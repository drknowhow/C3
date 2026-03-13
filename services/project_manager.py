"""Global project registry and session manager for C3."""

import json
import os
import socket
import subprocess
import sys
import time
import urllib.request
import urllib.error
from datetime import datetime, timezone
from pathlib import Path

from services.activity_log import ActivityLog

_GLOBAL_C3_DIR = Path.home() / ".c3"
_PROJECTS_FILE = _GLOBAL_C3_DIR / "projects.json"
_REGISTRY_FILE = _GLOBAL_C3_DIR / "registry.json"
_SESSION_ACTIVITY_GRACE_SECONDS = 20 * 60


def _pythonw() -> str:
    """Return pythonw.exe when available for hidden-background launches on Windows."""
    candidate = Path(sys.executable).parent / "pythonw.exe"
    return str(candidate) if candidate.exists() else sys.executable


class ProjectManager:
    """Manages the global C3 project registry stored in ~/.c3/projects.json."""

    def __init__(self):
        _GLOBAL_C3_DIR.mkdir(parents=True, exist_ok=True)

    def _read_projects(self) -> list:
        try:
            if _PROJECTS_FILE.exists():
                with open(_PROJECTS_FILE, encoding="utf-8") as f:
                    return json.load(f).get("projects", [])
        except Exception:
            pass
        return []

    def _write_projects(self, projects: list):
        _GLOBAL_C3_DIR.mkdir(parents=True, exist_ok=True)
        with open(_PROJECTS_FILE, "w", encoding="utf-8") as f:
            json.dump({"projects": projects}, f, indent=2)

    def _read_registry(self) -> list:
        try:
            if _REGISTRY_FILE.exists():
                with open(_REGISTRY_FILE, encoding="utf-8") as f:
                    return json.load(f)
        except Exception:
            pass
        return []

    def _port_alive(self, port: int) -> bool:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.3):
                return True
        except Exception:
            return False

    def _verify_c3_session(self, port: int) -> bool:
        """Verify that a given port is actually a C3 session UI."""
        try:
            url = f"http://127.0.0.1:{port}/api/health"
            with urllib.request.urlopen(url, timeout=0.8) as r:
                data = json.loads(r.read().decode("utf-8"))
                is_c3 = data.get("service") in {"c3-ui", "c3-hub"}
                # Also accept if 'sources' key is present (for older versions or custom UIs)
                return is_c3 or "sources" in data
        except Exception:
            return False

    def _parse_timestamp(self, value: str | None) -> datetime | None:
        if not value:
            return None
        try:
            normalized = str(value).strip().replace("Z", "+00:00")
            dt = datetime.fromisoformat(normalized)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except Exception:
            return None

    def _read_project_config(self, path: str) -> dict:
        config_path = Path(path) / ".c3" / "config.json"
        if config_path.exists():
            try:
                with open(config_path, encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {}

    def _get_budget_info(self, path: str) -> dict | None:
        """Read the context budget from the project's .c3 directory."""
        budget_path = Path(path) / ".c3" / "context_budget.json"
        if budget_path.exists():
            try:
                with open(budget_path, encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return None

    def _get_live_session_info(self, path: str) -> dict | None:
        """Return live session info inferred from the project's activity log."""
        try:
            activity = ActivityLog(path)
            starts = activity.get_recent(limit=1, event_type="session_start")
            if not starts:
                return None
            start_event = starts[0]
            session_id = start_event.get("session_id")
            started = start_event.get("timestamp")
            if not session_id or not started:
                return None

            saves = activity.get_recent(limit=1, event_type="session_save")
            if saves and saves[0].get("session_id") == session_id:
                return None

            recent = activity.get_recent(limit=1, since=started)
            last_activity = recent[0].get("timestamp") if recent else started
            started_dt = self._parse_timestamp(started)
            last_activity_dt = self._parse_timestamp(last_activity)
            if not started_dt or not last_activity_dt:
                return None
            now = datetime.now(timezone.utc)
            idle_seconds = max(0, int((now - last_activity_dt).total_seconds()))
            if idle_seconds > _SESSION_ACTIVITY_GRACE_SECONDS:
                return None
            duration_seconds = max(0, int((now - started_dt).total_seconds()))
            return {
                "session_id": session_id,
                "started_at": started,
                "last_activity": last_activity,
                "description": start_event.get("description", ""),
                "duration_seconds": duration_seconds,
                "idle_seconds": idle_seconds,
            }
        except Exception:
            return None

    def _get_last_session_timestamp(
        self, path: str, stored_value: str | None = None, live_session: dict | None = None
    ) -> str | None:
        """Return the most recent known session timestamp for a project."""
        latest_dt = None
        latest_raw = None

        def remember(value: str | None):
            nonlocal latest_dt, latest_raw
            dt = self._parse_timestamp(value)
            if dt and (latest_dt is None or dt > latest_dt):
                latest_dt = dt
                latest_raw = value

        remember(stored_value)
        if live_session:
            remember(live_session.get("last_activity"))
            remember(live_session.get("started_at"))
        try:
            activity = ActivityLog(path)
            remember((activity.get_recent(limit=1, event_type="session_save") or [{}])[0].get("timestamp"))
            remember((activity.get_recent(limit=1, event_type="session_start") or [{}])[0].get("timestamp"))
        except Exception:
            pass
        return latest_raw

    def add_project(self, path: str, name: str = None) -> dict:
        path = str(Path(path).resolve())
        projects = self._read_projects()
        for p in projects:
            if p["path"] == path:
                return p
        cfg = self._read_project_config(path)
        entry = {
            "name": name or Path(path).name,
            "path": path,
            "ide": cfg.get("ide", "unknown"),
            "added_at": datetime.utcnow().isoformat() + "Z",
            "last_session": None,
            "tags": [],
            "notes": "",
        }
        projects.append(entry)
        self._write_projects(projects)
        return entry

    def remove_project(self, path: str) -> bool:
        path = str(Path(path).resolve())
        projects = self._read_projects()
        filtered = [p for p in projects if p["path"] != path]
        if len(filtered) < len(projects):
            self._write_projects(filtered)
            return True
        return False

    def sweep_registry(self):
        """Remove stale registry entries (dead ports). Call on hub startup."""
        registry = self._read_registry()
        if not registry:
            return
        valid = [e for e in registry if e.get("port") and self._port_alive(e["port"])]
        if len(valid) != len(registry):
            try:
                with open(_REGISTRY_FILE, "w", encoding="utf-8") as f:
                    json.dump(valid, f, indent=2)
            except Exception:
                pass

    def list_projects(self) -> list:
        projects = self._read_projects()
        registry = self._read_registry()
        ui_active_by_path: dict = {}
        valid_registry = []
        registry_changed = False

        for entry in registry:
            port = entry.get("port")
            proj_path = entry.get("project_path", "")
            if port and self._port_alive(port):
                if self._verify_c3_session(port):
                    ui_active_by_path[proj_path] = entry
                    valid_registry.append(entry)
                else:
                    registry_changed = True
            else:
                registry_changed = True

        if registry_changed:
            try:
                with open(_REGISTRY_FILE, "w", encoding="utf-8") as f:
                    json.dump(valid_registry, f, indent=2)
            except Exception:
                pass

        result = []
        for p in projects:
            enriched = dict(p)
            path_accessible = Path(p["path"]).is_dir()
            enriched["accessible"] = path_accessible
            ui_active = ui_active_by_path.get(p["path"])
            live_session = self._get_live_session_info(p["path"]) if path_accessible else None
            enriched["ui_active"] = ui_active is not None
            enriched["session_active"] = live_session is not None
            # A project is active if either the web UI is live or the activity log shows a
            # currently running C3 session. The hub card should not fall back to "idle"
            # just because the session has no live UI port.
            enriched["active"] = enriched["ui_active"] or enriched["session_active"]
            enriched["port"] = ui_active["port"] if ui_active else None
            enriched["budget"] = self._get_budget_info(p["path"]) if enriched["active"] else None
            enriched["started_at"] = (
                ui_active["started_at"]
                if ui_active
                else (live_session["started_at"] if live_session else None)
            )
            enriched["live_session_id"] = (
                live_session["session_id"] if live_session else None
            )
            enriched["last_activity"] = (
                live_session["last_activity"] if live_session else None
            )
            enriched["session_description"] = (
                live_session["description"] if live_session else ""
            )
            enriched["last_session"] = (
                self._get_last_session_timestamp(p["path"], p.get("last_session"), live_session)
                if path_accessible else p.get("last_session")
            )
            cfg = self._read_project_config(p["path"]) if path_accessible else {}
            if cfg:
                enriched["ide"] = cfg.get("ide", p.get("ide", "unknown"))
                enriched["c3_version"] = cfg.get("version")
                try:
                    from core.ide import PROFILES
                    prof = PROFILES.get(enriched["ide"])
                    if prof:
                        if prof.config_path_global:
                            mf = Path.home() / prof.config_path
                        else:
                            mf = Path(p["path"]) / prof.config_path
                        enriched["mcp_installed"] = mf.exists()
                        mcp_cfg = cfg.get("mcp", {})
                        enriched["mcp_mode"] = mcp_cfg.get("mode") if isinstance(mcp_cfg, dict) else None
                except Exception:
                    pass
            result.append(enriched)
        return result

    def get_active_sessions(self) -> list:
        active = []
        for e in self._read_registry():
            port = e.get("port", 0)
            if port and self._port_alive(port) and self._verify_c3_session(port):
                active.append(e)
        
        for project in self.list_projects():
            if project.get("session_active") and not project.get("ui_active"):
                active.append(
                    {
                        "project_path": project["path"],
                        "project_name": project.get("name", Path(project["path"]).name),
                        "port": None,
                        "started_at": project.get("started_at"),
                        "live_session_id": project.get("live_session_id"),
                    }
                )
        return active

    def launch_session(self, path: str) -> dict:
        """Launch a C3 UI session for a project.

        Returns dict with 'launched' bool and optional 'error' string.
        """
        if not Path(path).is_dir():
            return {"launched": False, "error": f"Project path not accessible: {path}"}
        c3_py = Path(__file__).parent.parent / "cli" / "c3.py"
        env = os.environ.copy()
        env["PYTHONPATH"] = str(Path(__file__).parent.parent)
        kwargs = {}
        cmd = [sys.executable, str(c3_py), "ui", "--no-browser", "--silent"]
        log_dir = Path(path) / ".c3"
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = log_dir / "ui.log"
        if sys.platform == "win32":
            cmd[0] = _pythonw()
            kwargs["creationflags"] = (
                subprocess.DETACHED_PROCESS
                | subprocess.CREATE_NEW_PROCESS_GROUP
                | subprocess.CREATE_NO_WINDOW
            )
            kwargs["close_fds"] = True
            kwargs["stdout"] = open(log_file, "a", encoding="utf-8")
            kwargs["stderr"] = subprocess.STDOUT
            kwargs["stdin"] = subprocess.DEVNULL
        else:
            kwargs["start_new_session"] = True
            kwargs["stdout"] = open(log_file, "a", encoding="utf-8")
            kwargs["stderr"] = subprocess.STDOUT
        try:
            subprocess.Popen(cmd, cwd=path, env=env, **kwargs)
            return {"launched": True}
        except Exception as e:
            return {"launched": False, "error": str(e)}

    def stop_session(self, port: int) -> bool:
        try:
            kwargs = {}
            if sys.platform == "win32":
                kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
            if sys.platform == "win32":
                result = subprocess.run(f"netstat -ano | findstr :{port}", shell=True, capture_output=True, text=True, **kwargs)
                pids = set()
                for line in result.stdout.strip().splitlines():
                    if f":{port}" in line and "LISTENING" in line:
                        parts = line.strip().split()
                        if len(parts) >= 5:
                            pids.add(parts[-1])
                for pid in pids:
                    subprocess.run(f"taskkill /PID {pid} /F", shell=True, capture_output=True, **kwargs)
            else:
                subprocess.run(f"lsof -ti:{port} | xargs kill -9", shell=True, capture_output=True)
            return True
        except Exception:
            return False

    def end_mcp_session(self, path: str) -> bool:
        """End an MCP-only session by writing a session_save event to the activity log."""
        live = self._get_live_session_info(path)
        if not live:
            return False
        activity = ActivityLog(path)
        activity.log("session_save", {"session_id": live["session_id"], "source": "hub"})
        return True

    def update_last_session(self, path: str):
        path = str(Path(path).resolve())
        projects = self._read_projects()
        for p in projects:
            if p["path"] == path:
                p["last_session"] = datetime.utcnow().isoformat() + "Z"
                break
        self._write_projects(projects)

    def get_project_details(self, path: str) -> dict:
        path = str(Path(path).resolve())
        cfg = self._read_project_config(path)
        ide = cfg.get("ide", "unknown")
        mcp_cfg = cfg.get("mcp", {})
        mcp_mode = mcp_cfg.get("mode", "unknown") if isinstance(mcp_cfg, dict) else "unknown"
        mcp_installed = False
        mcp_config_path = None
        mcp_servers: list = []
        try:
            from core.ide import PROFILES
            profile = PROFILES.get(ide)
            if profile:
                if profile.config_path_global:
                    mcp_file = Path.home() / profile.config_path
                else:
                    mcp_file = Path(path) / profile.config_path
                if mcp_file.exists():
                    mcp_installed = True
                    mcp_config_path = str(mcp_file)
                    if profile.config_format == "json":
                        with open(mcp_file, encoding="utf-8") as f:
                            mcp_data = json.load(f)
                        servers = mcp_data.get(profile.config_key, {})
                        if isinstance(servers, dict):
                            for name, conf in servers.items():
                                mcp_servers.append({
                                    "name": name,
                                    "command": conf.get("command", ""),
                                    "args": conf.get("args", []),
                                    "type": conf.get("type", ""),
                                    "env_keys": list((conf.get("env") or {}).keys()),
                                })
                    elif profile.config_format == "toml":
                        try:
                            import tomllib
                        except ImportError:
                            try:
                                import tomli as tomllib
                            except ImportError:
                                tomllib = None
                        if tomllib:
                            with open(mcp_file, "rb") as f:
                                toml_data = tomllib.load(f)
                            for name, conf in toml_data.get("mcp_servers", {}).items():
                                mcp_servers.append({
                                    "name": name,
                                    "command": conf.get("command", ""),
                                    "args": conf.get("args", []),
                                    "type": "",
                                    "env_keys": [],
                                })
        except Exception:
            pass
        return {
            "path": path,
            "c3_version": cfg.get("version"),
            "ide": ide,
            "mcp_mode": mcp_mode,
            "mcp_installed": mcp_installed,
            "mcp_config_path": mcp_config_path,
            "mcp_servers": mcp_servers,
            "initialized": bool(cfg),
        }

    def update_project(self, path: str, **fields) -> bool:
        """Update editable project fields: name, tags, notes."""
        path = str(Path(path).resolve())
        projects = self._read_projects()
        allowed = {"name", "tags", "notes"}
        for p in projects:
            if p["path"] == path:
                for k, v in fields.items():
                    if k in allowed:
                        p[k] = v
                self._write_projects(projects)
                return True
        return False

    def rename_project(self, path: str, new_name: str) -> bool:
        path = str(Path(path).resolve())
        projects = self._read_projects()
        for p in projects:
            if p["path"] == path:
                p["name"] = new_name
                self._write_projects(projects)
                return True
        return False
