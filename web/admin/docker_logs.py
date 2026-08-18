"""Read-only Docker container log access for the admin panel.

Deliberately minimal: only `list_containers`/`tail_logs` are exposed — no
exec/start/stop/remove anywhere in this module or its callers. The Docker
client is constructed lazily (first use inside a route handler), never at
import time, so importing web.app never fails just because an environment
(the test suite, a misconfigured host) has no /var/run/docker.sock.

Not scoped to one compose project — this is the same Docker daemon a
separate stack (e.g. speechkit's) runs on too, so its containers are visible
here as well.
"""
import docker
from docker.errors import DockerException, NotFound

_client: docker.DockerClient | None = None


class DockerUnavailable(Exception):
    """The Docker socket/daemon couldn't be reached."""


class ContainerNotFound(Exception):
    """No container with that name on this daemon."""


def _get_client() -> docker.DockerClient:
    global _client
    if _client is None:
        try:
            client = docker.DockerClient(base_url="unix://var/run/docker.sock")
            client.ping()
        except DockerException as e:
            raise DockerUnavailable(str(e)) from e
        _client = client
    return _client


def list_containers() -> list[dict]:
    """name/image/status for every container on the host daemon.

    Reads the image reference straight off each container's own listing
    attrs (`Image`, the name/tag it was created from) rather than resolving
    a live Image object — a container can outlive the image it was created
    from (removed/pruned since), and `container.image` does its own API
    call that raises `ImageNotFound` in exactly that case.
    """
    try:
        containers = _get_client().containers.list(all=True)
        return [
            {"name": c.name, "image": c.attrs.get("Image", ""), "status": c.status}
            for c in containers
        ]
    except DockerException as e:
        raise DockerUnavailable(str(e)) from e


def tail_logs(name: str, lines: int = 200) -> str:
    """Last `lines` of a container's stdout/stderr, timestamped."""
    try:
        container = _get_client().containers.get(name)
    except NotFound as e:
        raise ContainerNotFound(name) from e
    except DockerException as e:
        raise DockerUnavailable(str(e)) from e
    try:
        raw = container.logs(tail=lines, timestamps=True)
    except DockerException as e:
        raise DockerUnavailable(str(e)) from e
    return raw.decode("utf-8", errors="replace")
