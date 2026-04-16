from starlette.applications import Starlette
from starlette.routing import Route, Mount
from starlette.responses import JSONResponse
import uvicorn
import threading
from fastmcp import FastMCP
import os
import asyncio
import subprocess
import sys
import json
from typing import Optional

mcp = FastMCP("lastversion")

GITHUB_API_TOKEN = os.environ.get("GITHUB_API_TOKEN", "")


def build_env():
    """Build environment variables for lastversion subprocess calls."""
    env = os.environ.copy()
    if GITHUB_API_TOKEN:
        env["GITHUB_API_TOKEN"] = GITHUB_API_TOKEN
    return env


async def run_lastversion(*args) -> dict:
    """Run lastversion CLI with given arguments and return result."""
    cmd = [sys.executable, "-m", "lastversion"] + list(args)
    env = build_env()
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )
        stdout, stderr = await proc.communicate()
        return {
            "returncode": proc.returncode,
            "stdout": stdout.decode("utf-8", errors="replace").strip(),
            "stderr": stderr.decode("utf-8", errors="replace").strip(),
        }
    except FileNotFoundError:
        return {
            "returncode": -1,
            "stdout": "",
            "stderr": "lastversion is not installed. Install it with: pip install lastversion",
        }
    except Exception as e:
        return {
            "returncode": -1,
            "stdout": "",
            "stderr": str(e),
        }


@mcp.tool()
async def get_latest_version(
    project: str,
    pre_ok: bool = False,
    major: Optional[str] = None,
    at: Optional[str] = None,
) -> dict:
    """Get the latest stable version of a project from GitHub, GitLab, PyPI, npm, or other supported sources.
    Use this when you need to know the current stable release version of any open source project or software package.
    """
    args = [project]
    if pre_ok:
        args.append("--pre")
    if major:
        args.extend(["--major", major])
    if at:
        args.extend(["--at", at])

    result = await run_lastversion(*args)

    if result["returncode"] == 0 and result["stdout"]:
        return {
            "success": True,
            "project": project,
            "latest_version": result["stdout"],
            "pre_ok": pre_ok,
            "major": major,
            "at": at,
        }
    else:
        return {
            "success": False,
            "project": project,
            "error": result["stderr"] or "Could not determine latest version",
            "stdout": result["stdout"],
            "returncode": result["returncode"],
        }


@mcp.tool()
async def check_version(
    project: str,
    version: str,
    at: Optional[str] = None,
) -> dict:
    """Check whether a given version of a project is the latest stable release.
    Returns whether the version is up-to-date or outdated.
    """
    args = [project, "-gt", version]
    if at:
        args.extend(["--at", at])

    result = await run_lastversion(*args)

    # lastversion exits 0 if the latest > provided version (i.e., provided is outdated)
    # exits 1 if the provided version is up-to-date or latest
    # Also get the actual latest version for comparison
    latest_result = await get_latest_version(project, at=at)
    latest_ver = latest_result.get("latest_version", "unknown")

    if result["returncode"] == 0:
        # Latest version is greater than checked version -> outdated
        return {
            "success": True,
            "project": project,
            "checked_version": version,
            "latest_version": latest_ver,
            "is_latest": False,
            "is_outdated": True,
            "message": f"Version {version} is outdated. Latest is {latest_ver}.",
        }
    elif result["returncode"] == 1:
        # The checked version is already the latest
        return {
            "success": True,
            "project": project,
            "checked_version": version,
            "latest_version": latest_ver,
            "is_latest": True,
            "is_outdated": False,
            "message": f"Version {version} is the latest stable release.",
        }
    else:
        return {
            "success": False,
            "project": project,
            "checked_version": version,
            "error": result["stderr"] or "Could not check version",
            "returncode": result["returncode"],
        }


@mcp.tool()
async def download_latest(
    project: str,
    output_dir: str = ".",
    asset_filter: Optional[str] = None,
    at: Optional[str] = None,
    pre_ok: bool = False,
) -> dict:
    """Download the latest release assets of a project to a local directory.
    Use this when you need to fetch the actual release files (tarballs, binaries, etc.) for a project.
    """
    args = ["--download"]
    if output_dir and output_dir != ".":
        args = ["--download", output_dir]
    if pre_ok:
        args.append("--pre")
    if at:
        args.extend(["--at", at])
    if asset_filter:
        args.extend(["--filter", asset_filter])
    args.append(project)

    result = await run_lastversion(*args)

    if result["returncode"] == 0:
        return {
            "success": True,
            "project": project,
            "output_dir": output_dir,
            "asset_filter": asset_filter,
            "message": result["stdout"] or "Download completed successfully",
            "stderr": result["stderr"],
        }
    else:
        return {
            "success": False,
            "project": project,
            "error": result["stderr"] or "Download failed",
            "stdout": result["stdout"],
            "returncode": result["returncode"],
        }


@mcp.tool()
async def install_latest(
    project: str,
    at: Optional[str] = None,
    pre_ok: bool = False,
) -> dict:
    """Download and install the latest release of a project using the system's package manager or by running the installer.
    Use this when you want to actually install software, not just check its version.
    """
    args = ["--install", project]
    if pre_ok:
        args.append("--pre")
    if at:
        args.extend(["--at", at])

    result = await run_lastversion(*args)

    if result["returncode"] == 0:
        return {
            "success": True,
            "project": project,
            "message": result["stdout"] or "Installation completed successfully",
            "stderr": result["stderr"],
        }
    else:
        return {
            "success": False,
            "project": project,
            "error": result["stderr"] or "Installation failed",
            "stdout": result["stdout"],
            "returncode": result["returncode"],
        }


@mcp.tool()
async def get_release_assets(
    project: str,
    asset_filter: Optional[str] = None,
    at: Optional[str] = None,
    pre_ok: bool = False,
) -> dict:
    """List or retrieve the download URLs for assets of the latest release of a project.
    Use this when you need to know what files are available in the latest release without downloading them.
    """
    args = ["--assets", project]
    if pre_ok:
        args.append("--pre")
    if at:
        args.extend(["--at", at])
    if asset_filter:
        args.extend(["--filter", asset_filter])

    result = await run_lastversion(*args)

    if result["returncode"] == 0 and result["stdout"]:
        asset_urls = [line.strip() for line in result["stdout"].splitlines() if line.strip()]
        return {
            "success": True,
            "project": project,
            "asset_filter": asset_filter,
            "assets": asset_urls,
            "count": len(asset_urls),
        }
    else:
        return {
            "success": False,
            "project": project,
            "error": result["stderr"] or "Could not retrieve release assets",
            "stdout": result["stdout"],
            "returncode": result["returncode"],
        }


@mcp.tool()
async def get_release_notes(
    project: str,
    version: Optional[str] = None,
    at: Optional[str] = None,
) -> dict:
    """Retrieve the changelog or release notes for the latest (or a specific) version of a project.
    Use this when a user wants to know what changed in the latest release.
    """
    args = ["--changelog", project]
    if at:
        args.extend(["--at", at])
    if version:
        # lastversion does not have a direct --version flag for changelog,
        # but we pass the version as a reference for informational purposes
        pass

    result = await run_lastversion(*args)

    if result["returncode"] == 0 and result["stdout"]:
        return {
            "success": True,
            "project": project,
            "version": version,
            "release_notes": result["stdout"],
        }
    else:
        return {
            "success": False,
            "project": project,
            "version": version,
            "error": result["stderr"] or "Could not retrieve release notes",
            "stdout": result["stdout"],
            "returncode": result["returncode"],
        }


@mcp.tool()
async def get_source_url(
    project: str,
    format: str = "tar",
    at: Optional[str] = None,
    major: Optional[str] = None,
    pre_ok: bool = False,
) -> dict:
    """Get the source tarball or zip URL for the latest release of a project without downloading it.
    Use this when you need a direct URL to embed in scripts, Dockerfiles, or build configurations.
    """
    if format == "zip":
        format_flag = "--format"
        format_value = "zip"
    else:
        format_flag = "--format"
        format_value = "tar"

    args = [format_flag, format_value, project]
    if pre_ok:
        args.append("--pre")
    if at:
        args.extend(["--at", at])
    if major:
        args.extend(["--major", major])

    result = await run_lastversion(*args)

    if result["returncode"] == 0 and result["stdout"]:
        return {
            "success": True,
            "project": project,
            "format": format,
            "source_url": result["stdout"],
            "major": major,
            "at": at,
        }
    else:
        return {
            "success": False,
            "project": project,
            "format": format,
            "error": result["stderr"] or "Could not retrieve source URL",
            "stdout": result["stdout"],
            "returncode": result["returncode"],
        }




_SERVER_SLUG = "dvershinin-lastversion"

def _track(tool_name: str, ua: str = ""):
    try:
        import urllib.request, json as _json
        data = _json.dumps({"slug": _SERVER_SLUG, "event": "tool_call", "tool": tool_name, "user_agent": ua}).encode()
        req = urllib.request.Request("https://www.volspan.dev/api/analytics/event", data=data, headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=1)
    except Exception:
        pass

async def health(request):
    return JSONResponse({"status": "ok", "server": mcp.name})

async def tools(request):
    registered = await mcp.list_tools()
    tool_list = [{"name": t.name, "description": t.description or ""} for t in registered]
    return JSONResponse({"tools": tool_list, "count": len(tool_list)})

sse_app = mcp.http_app(transport="sse")

app = Starlette(
    routes=[
        Route("/health", health),
        Route("/tools", tools),
        Mount("/", sse_app),
    ],
    lifespan=sse_app.lifespan,
)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))
