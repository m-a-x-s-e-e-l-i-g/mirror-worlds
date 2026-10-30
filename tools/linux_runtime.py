"""Run the same Linux build/test commands through Docker or Windows WSL."""
from pathlib import Path
import subprocess


class LinuxRuntime:
    def __init__(self, root, kind="docker", image="glitchlock-ml-builder:bookworm", distro="Ubuntu", wsl_user=None):
        self.root = Path(root).resolve()
        self.kind, self.image, self.distro = kind, image, distro
        self.wsl_user = wsl_user
        if kind == "wsl":
            self.linux_root = subprocess.check_output(
                ["wsl", "--distribution", distro, "--exec", "wslpath", "-a", str(self.root)], text=True).strip()
        elif kind == "docker":
            self.linux_root = "/work"
        else:
            raise ValueError("Unknown Linux runtime: " + kind)

    def prefix(self, cwd="."):
        relative = Path(cwd)
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError("Runtime working directory must stay within the workspace")
        directory = self.linux_root + ("/" + relative.as_posix() if str(relative) != "." else "")
        if self.kind == "wsl":
            user = ["--user", self.wsl_user] if self.wsl_user else []
            return ["wsl", "--distribution", self.distro, *user, "--cd", directory, "--exec"]
        return ["docker", "run", "--rm", "--mount", f"type=bind,source={self.root},target=/work",
                "-w", directory, self.image]

    def run(self, *command, cwd=".", **kwargs):
        return subprocess.run(self.prefix(cwd) + list(command), check=True, **kwargs)

    def output(self, *command, cwd="."):
        return subprocess.check_output(self.prefix(cwd) + list(command), text=True)
