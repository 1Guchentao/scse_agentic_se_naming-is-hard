"""A private, measured GPU session; no downloads or automatic retries."""

from contextlib import contextmanager
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import threading
import time
from urllib.request import ProxyHandler, Request, build_opener

import psutil

from workspace_io import decode_json, save_json

MODEL = "qwen2.5:3b"
THREAD_ENV = {"OMP_NUM_THREADS": "2", "OPENBLAS_NUM_THREADS": "2",
              "MKL_NUM_THREADS": "2", "NUMEXPR_NUM_THREADS": "2"}
HIDDEN = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0


def hardware():
    output = subprocess.check_output(
        ["nvidia-smi", "--query-gpu=memory.free,temperature.gpu",
         "--format=csv,noheader,nounits", "--id=0"],
        text=True, timeout=10, creationflags=HIDDEN)
    memory, temperature = [int(value.strip()) for value in output.strip().split(",")]
    return {"available_ram_gib": round(psutil.virtual_memory().available / 2**30, 3),
            "gpu_free_mib": memory, "gpu_temperature_c": temperature}


class GpuSession:
    def __init__(self, folder, backend="vulkan", device=1, port=11523):
        self.folder = Path(folder)
        self.backend, self.device, self.port = backend, device, port
        self.url = f"http://127.0.0.1:{port}"
        self.opener = build_opener(ProxyHandler({}))
        self.process = None
        self.log = None
        self.stop = threading.Event()
        self.fault = None
        self.samples = []
        self.guard = None

    def http(self, path, data=None, timeout=240):
        request = Request(self.url + path,
                          data=None if data is None else json.dumps(data).encode(),
                          headers={"Content-Type": "application/json"})
        with self.opener.open(request, timeout=timeout) as response:
            return decode_json(response.read().decode())

    def _watch(self):
        while not self.stop.wait(2):
            try:
                sample = hardware()
                self.samples.append({"time": datetime.now(timezone.utc).isoformat(), **sample})
                if sample["available_ram_gib"] < 1.25 or sample["gpu_temperature_c"] >= 80:
                    self.fault = (f"Resource limit reached: RAM={sample['available_ram_gib']} GiB, "
                                  f"GPU={sample['gpu_temperature_c']} C.")
                    self._terminate()
                    return
            except Exception as error:
                self.fault = f"Resource monitor stopped: {error}"
                self._terminate()
                return

    def _terminate(self):
        if self.process is None or self.process.poll() is not None:
            return
        try:
            parent = psutil.Process(self.process.pid)
            owned = parent.children(recursive=True) + [parent]
        except psutil.NoSuchProcess:
            return
        for process in owned:
            try:
                process.terminate()
            except psutil.NoSuchProcess:
                pass
        _, alive = psutil.wait_procs(owned, timeout=5)
        for process in alive:
            try:
                process.kill()
            except psutil.NoSuchProcess:
                pass
        psutil.wait_procs(alive, timeout=5)
        self.process.wait(timeout=10)

    def __enter__(self):
        self.folder.mkdir(parents=True, exist_ok=False)
        try:
            initial = hardware()
            save_json(self.folder / "startup.json", initial)
            if initial["available_ram_gib"] < 4.5 or initial["gpu_free_mib"] < 4500:
                raise RuntimeError("Need 4.5 GiB available RAM and 4500 MiB free GPU memory.")
            if initial["gpu_temperature_c"] >= 65:
                raise RuntimeError("Let the GPU cool below 65 C before starting.")
            binary = shutil.which("ollama")
            if not binary:
                raise RuntimeError("Ollama is not installed; no model download was attempted.")
            for process in psutil.process_iter(["name"]):
                if "ollama" in (process.info["name"] or "").lower():
                    raise RuntimeError("Another Ollama process is running; it was left untouched.")
            with socket.socket() as probe:
                probe.bind(("127.0.0.1", self.port))
            environment = {**os.environ, **THREAD_ENV,
                           "OLLAMA_HOST": f"127.0.0.1:{self.port}",
                           "OLLAMA_NUM_PARALLEL": "1", "OLLAMA_MAX_LOADED_MODELS": "1",
                           "OLLAMA_KEEP_ALIVE": "30s", "OLLAMA_CONTEXT_LENGTH": "4096"}
            if self.backend == "vulkan":
                environment.update(OLLAMA_VULKAN="1", GGML_VK_VISIBLE_DEVICES=str(self.device),
                                   CUDA_VISIBLE_DEVICES="-1")
            self.log = (self.folder / "service.log").open("w", encoding="utf-8")
            self.process = subprocess.Popen([binary, "serve"], env=environment,
                                            stdout=self.log, stderr=subprocess.STDOUT,
                                            creationflags=HIDDEN)
            for _ in range(60):
                if self.process.poll() is not None:
                    raise RuntimeError("The private model service exited during startup.")
                try:
                    tags = self.http("/api/tags", timeout=2)
                    break
                except OSError:
                    time.sleep(1)
            else:
                raise RuntimeError("Private service startup timed out.")
            if MODEL not in {entry.get("name") for entry in tags.get("models", [])}:
                raise RuntimeError(f"{MODEL} is not already installed; no download was attempted.")
            save_json(self.folder / "service.json",
                      {"model": MODEL, "port": self.port, "backend": self.backend,
                       "device": self.device, "cpu_threads": 2, "pid": self.process.pid})
            self.guard = threading.Thread(target=self._watch, daemon=True)
            self.guard.start()
            return self
        except BaseException:
            self.__exit__(None, None, None)
            raise

    def ask(self, stage, instructions, context, *, response_shape=None, trace_folder=None):
        if self.fault:
            raise RuntimeError(self.fault)
        for _ in range(120):
            if hardware()["gpu_temperature_c"] < 65:
                break
            time.sleep(2)
        else:
            raise RuntimeError("GPU cooling wait exceeded four minutes.")
        if self.fault:
            raise RuntimeError(self.fault)
        data = {"model": MODEL, "stream": False, "keep_alive": "30s",
                "messages": [{"role": "system", "content": instructions},
                             {"role": "user", "content": context if isinstance(context, str)
                              else json.dumps(context, ensure_ascii=False)}],
                "options": {"num_gpu": 99, "num_thread": 2, "num_ctx": 4096,
                            "num_batch": 64, "num_predict": 2200, "temperature": 0, "seed": 31}}
        if response_shape is not None:
            data["format"] = response_shape
        started = datetime.now(timezone.utc).isoformat()
        record = {"stage": stage, "started": started, "request": data}
        destination = Path(trace_folder or self.folder) / (stage + ".json")
        try:
            response = self.http("/api/chat", data)
            record["response"] = response
            record["loaded_models"] = self.http("/api/ps", timeout=10)
            record["hardware"] = hardware()
            loaded = [item for item in record["loaded_models"].get("models", [])
                      if item.get("name") == MODEL]
            if not loaded or loaded[0].get("size_vram", 0) < loaded[0].get("size", 1) * 0.9:
                raise RuntimeError("The model was not fully loaded on GPU.")
            if response.get("done") is not True or response.get("done_reason") == "length":
                raise ValueError("The model reply is incomplete.")
            text = response.get("message", {}).get("content")
            if not isinstance(text, str) or not text.strip():
                raise ValueError("The model returned no text.")
            if self.fault:
                raise RuntimeError(self.fault)
            record["status"] = "received"
            return text
        except BaseException as error:
            record["status"] = "error"
            record["error"] = self.fault or str(error)
            if self.fault:
                raise RuntimeError(self.fault) from error
            raise
        finally:
            record["finished"] = datetime.now(timezone.utc).isoformat()
            unload_error = None
            if self.process is not None and self.process.poll() is None:
                try:
                    self.http("/api/generate", {"model": MODEL, "keep_alive": 0}, timeout=30)
                except OSError as error:
                    unload_error = str(error)
            record["unload_error"] = unload_error
            save_json(destination, record)
            if unload_error and record["status"] == "received":
                raise RuntimeError("The private model could not be unloaded.")

    def __exit__(self, exc_type, exc, tb):
        self.stop.set()
        if self.guard is not None:
            self.guard.join(timeout=12)
        self._terminate()
        if self.log is not None:
            self.log.close()
        with socket.socket() as probe:
            listening = probe.connect_ex(("127.0.0.1", self.port)) == 0
        save_json(self.folder / "cleanup.json",
                  {"service_stopped": self.process is None or self.process.poll() is not None,
                   "port_closed": not listening, "monitor_fault": self.fault,
                   "samples": self.samples})


@contextmanager
def bind_existing_agents(session):
    import analyst_agent
    import planner_agent
    import developer_agent
    modules = (analyst_agent, planner_agent, developer_agent)
    previous = [module.ask for module in modules]
    try:
        for module in modules:
            module.ask = session.ask
        yield
    finally:
        for module, original in zip(modules, previous):
            module.ask = original
