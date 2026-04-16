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
import tempfile
import shutil
from typing import Optional

mcp = FastMCP("lastversion")

GITHUB_API_TOKEN = os.environ.get("GITHUB_API_TOKEN", "")


def build_env():
    """Build environment variables for subprocess calls."""
    env = os.environ.copy()
    if GITHUB_API_TOKEN:
        env["GITHUB_API_TOKEN"] = GITHUB_API_TOKEN
    return env


async def run_lastversion(*args, capture_output=True):
    """Run lastversion CLI command asynchronously."""
    cmd = [sys.executable, "-m", "lastversion"] + list(args)
    env = build_env()
    
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(
        None,
        lambda: subprocess.run(
            cmd,
            capture_output=capture_output,
            text=True,
            env=env,
            timeout=60
        )
    )
    return result


@mcp.tool()
async def get_latest_version(
    project: str,
    pre_ok: bool = False,
    major: Optional[str] = None,
    at: Optional[str] = None,
    format: str = "version"
) -> dict:
    """Get the latest stable version of a project from GitHub, GitLab, PyPI, npm, or other supported sources."""
    args = [project]
    
    if pre_ok:
        args.append("--pre")
    if major:
        args.extend(["--major", major])
    if at:
        args.extend(["--at", at])
    
    if format == "json":
        args.extend(["--format", "json"])
    elif format == "dict":
        args.extend(["--format", "dict"])
    # default is version string output
    
    try:
        result = await run_lastversion(*args)
        
        if result.returncode == 0:
            output = result.stdout.strip()
            if format == "json":
                try:
                    return {"success": True, "project": project, "data": json.loads(output)}
                except json.JSONDecodeError:
                    return {"success": True, "project": project, "version": output}
            else:
                return {"success": True, "project": project, "version": output}
        else:
            return {
                "success": False,
                "project": project,
                "error": result.stderr.strip() or "No version found or project not found",
                "returncode": result.returncode
            }
    except subprocess.TimeoutExpired:
        return {"success": False, "project": project, "error": "Request timed out after 60 seconds"}
    except Exception as e:
        return {"success": False, "project": project, "error": str(e)}


@mcp.tool()
async def check_version(
    project: str,
    version: str,
    pre_ok: bool = False,
    at: Optional[str] = None
) -> dict:
    """Check if a given version is the latest for a project, or compare a local version against the latest."""
    # First get the latest version
    get_args = [project]
    if pre_ok:
        get_args.append("--pre")
    if at:
        get_args.extend(["--at", at])
    
    try:
        result = await run_lastversion(*get_args)
        
        if result.returncode != 0:
            return {
                "success": False,
                "project": project,
                "error": result.stderr.strip() or "Could not retrieve latest version",
                "returncode": result.returncode
            }
        
        latest_version = result.stdout.strip()
        
        # Compare versions using lastversion's format/comparison capability
        # Use the -eq flag style comparison
        eq_args = [version, "-eq", latest_version]
        eq_result = await run_lastversion(*eq_args)
        is_equal = eq_result.returncode == 0
        
        gt_args = [version, "-gt", latest_version]
        gt_result = await run_lastversion(*gt_args)
        is_newer = gt_result.returncode == 0
        
        lt_args = [version, "-lt", latest_version]
        lt_result = await run_lastversion(*lt_args)
        is_older = lt_result.returncode == 0
        
        status = "up_to_date" if is_equal else ("outdated" if is_older else "newer_than_latest")
        
        return {
            "success": True,
            "project": project,
            "checked_version": version,
            "latest_version": latest_version,
            "is_latest": is_equal,
            "is_outdated": is_older,
            "is_newer_than_latest": is_newer,
            "status": status
        }
    except subprocess.TimeoutExpired:
        return {"success": False, "project": project, "error": "Request timed out after 60 seconds"}
    except Exception as e:
        return {"success": False, "project": project, "error": str(e)}


@mcp.tool()
async def download_asset(
    project: str,
    output_dir: str = ".",
    asset_filter: Optional[str] = None,
    pre_ok: bool = False,
    at: Optional[str] = None
) -> dict:
    """Download the latest release asset or source archive for a project."""
    # Ensure output directory exists
    os.makedirs(output_dir, exist_ok=True)
    
    args = ["--download", project]
    
    if pre_ok:
        args.append("--pre")
    if at:
        args.extend(["--at", at])
    if asset_filter:
        args.extend(["--filter", asset_filter])
    if output_dir and output_dir != ".":
        args.extend(["--output-dir", output_dir])
    
    try:
        result = await run_lastversion(*args)
        
        if result.returncode == 0:
            output = result.stdout.strip()
            return {
                "success": True,
                "project": project,
                "output_dir": output_dir,
                "message": output or "Download completed successfully",
                "details": result.stderr.strip() if result.stderr else None
            }
        else:
            return {
                "success": False,
                "project": project,
                "error": result.stderr.strip() or result.stdout.strip() or "Download failed",
                "returncode": result.returncode
            }
    except subprocess.TimeoutExpired:
        return {"success": False, "project": project, "error": "Download timed out after 60 seconds"}
    except Exception as e:
        return {"success": False, "project": project, "error": str(e)}


@mcp.tool()
async def install_package(
    project: str,
    pre_ok: bool = False,
    at: Optional[str] = None,
    asset_filter: Optional[str] = None
) -> dict:
    """Download and install the latest release of a project using the system package manager or direct installation."""
    args = ["--install", project]
    
    if pre_ok:
        args.append("--pre")
    if at:
        args.extend(["--at", at])
    if asset_filter:
        args.extend(["--filter", asset_filter])
    
    try:
        result = await run_lastversion(*args)
        
        if result.returncode == 0:
            output = result.stdout.strip()
            return {
                "success": True,
                "project": project,
                "message": output or "Installation completed successfully",
                "details": result.stderr.strip() if result.stderr else None
            }
        else:
            return {
                "success": False,
                "project": project,
                "error": result.stderr.strip() or result.stdout.strip() or "Installation failed",
                "returncode": result.returncode
            }
    except subprocess.TimeoutExpired:
        return {"success": False, "project": project, "error": "Installation timed out after 60 seconds"}
    except Exception as e:
        return {"success": False, "project": project, "error": str(e)}


@mcp.tool()
async def get_release_info(
    project: str,
    pre_ok: bool = False,
    major: Optional[str] = None,
    at: Optional[str] = None
) -> dict:
    """Retrieve full metadata and release information about the latest version of a project."""
    args = [project, "--format", "json"]
    
    if pre_ok:
        args.append("--pre")
    if major:
        args.extend(["--major", major])
    if at:
        args.extend(["--at", at])
    
    try:
        result = await run_lastversion(*args)
        
        if result.returncode == 0:
            output = result.stdout.strip()
            try:
                data = json.loads(output)
                return {
                    "success": True,
                    "project": project,
                    "release_info": data
                }
            except json.JSONDecodeError:
                return {
                    "success": True,
                    "project": project,
                    "raw_output": output
                }
        else:
            return {
                "success": False,
                "project": project,
                "error": result.stderr.strip() or "Could not retrieve release info",
                "returncode": result.returncode
            }
    except subprocess.TimeoutExpired:
        return {"success": False, "project": project, "error": "Request timed out after 60 seconds"}
    except Exception as e:
        return {"success": False, "project": project, "error": str(e)}


@mcp.tool()
async def get_assets_list(
    project: str,
    pre_ok: bool = False,
    major: Optional[str] = None,
    at: Optional[str] = None
) -> dict:
    """List all downloadable assets available in the latest release of a project."""
    # Get release info in JSON format which includes assets
    args = [project, "--format", "json"]
    
    if pre_ok:
        args.append("--pre")
    if major:
        args.extend(["--major", major])
    if at:
        args.extend(["--at", at])
    
    try:
        result = await run_lastversion(*args)
        
        if result.returncode == 0:
            output = result.stdout.strip()
            try:
                data = json.loads(output)
                # Extract assets from the release info
                assets = []
                
                # Handle different possible JSON structures
                if isinstance(data, dict):
                    # Look for common asset fields in lastversion JSON output
                    if "assets" in data:
                        raw_assets = data["assets"]
                        if isinstance(raw_assets, list):
                            for asset in raw_assets:
                                if isinstance(asset, dict):
                                    assets.append({
                                        "name": asset.get("name", ""),
                                        "url": asset.get("browser_download_url", asset.get("url", "")),
                                        "size": asset.get("size", None),
                                        "content_type": asset.get("content_type", None),
                                        "download_count": asset.get("download_count", None)
                                    })
                                elif isinstance(asset, str):
                                    assets.append({"url": asset})
                        elif isinstance(raw_assets, dict):
                            for name, url in raw_assets.items():
                                assets.append({"name": name, "url": url})
                    
                    version_str = data.get("version", data.get("tag_name", ""))
                    tag = data.get("tag_name", "")
                    source_url = data.get("source", data.get("tarball_url", ""))
                    
                    # If no assets found but we have source URL, add it
                    if not assets and source_url:
                        assets.append({"name": "source_tarball", "url": source_url})
                    
                    return {
                        "success": True,
                        "project": project,
                        "version": version_str,
                        "tag": tag,
                        "assets": assets,
                        "asset_count": len(assets),
                        "full_data": data
                    }
                else:
                    return {
                        "success": True,
                        "project": project,
                        "raw_output": output,
                        "assets": []
                    }
            except json.JSONDecodeError:
                return {
                    "success": True,
                    "project": project,
                    "raw_output": output,
                    "assets": [],
                    "note": "Could not parse JSON output"
                }
        else:
            return {
                "success": False,
                "project": project,
                "error": result.stderr.strip() or "Could not retrieve assets",
                "returncode": result.returncode
            }
    except subprocess.TimeoutExpired:
        return {"success": False, "project": project, "error": "Request timed out after 60 seconds"}
    except Exception as e:
        return {"success": False, "project": project, "error": str(e)}


@mcp.tool()
async def get_source_url(
    project: str,
    asset_filter: Optional[str] = None,
    pre_ok: bool = False,
    at: Optional[str] = None
) -> dict:
    """Get the direct download URL for the latest release source archive or a specific asset of a project."""
    args = ["--source-only", project]
    
    if pre_ok:
        args.append("--pre")
    if at:
        args.extend(["--at", at])
    if asset_filter:
        args.extend(["--filter", asset_filter])
    
    try:
        result = await run_lastversion(*args)
        
        if result.returncode == 0:
            url = result.stdout.strip()
            if url:
                return {
                    "success": True,
                    "project": project,
                    "url": url,
                    "asset_filter": asset_filter
                }
            else:
                # Try alternative approach - get JSON and extract URL
                json_args = [project, "--format", "json"]
                if pre_ok:
                    json_args.append("--pre")
                if at:
                    json_args.extend(["--at", at])
                
                json_result = await run_lastversion(*json_args)
                if json_result.returncode == 0:
                    try:
                        data = json.loads(json_result.stdout.strip())
                        source_url = data.get("source", data.get("tarball_url", data.get("url", "")))
                        return {
                            "success": True,
                            "project": project,
                            "url": source_url,
                            "asset_filter": asset_filter,
                            "note": "URL extracted from JSON metadata"
                        }
                    except (json.JSONDecodeError, KeyError):
                        pass
                
                return {
                    "success": False,
                    "project": project,
                    "error": "No URL found in output"
                }
        else:
            # Fallback: try without --source-only flag and get JSON
            json_args = [project, "--format", "json"]
            if pre_ok:
                json_args.append("--pre")
            if at:
                json_args.extend(["--at", at])
            
            json_result = await run_lastversion(*json_args)
            if json_result.returncode == 0:
                try:
                    data = json.loads(json_result.stdout.strip())
                    source_url = data.get("source", data.get("tarball_url", data.get("url", "")))
                    if source_url:
                        return {
                            "success": True,
                            "project": project,
                            "url": source_url,
                            "asset_filter": asset_filter,
                            "note": "URL extracted from JSON metadata (fallback)"
                        }
                except (json.JSONDecodeError, KeyError):
                    pass
            
            return {
                "success": False,
                "project": project,
                "error": result.stderr.strip() or "Could not retrieve source URL",
                "returncode": result.returncode
            }
    except subprocess.TimeoutExpired:
        return {"success": False, "project": project, "error": "Request timed out after 60 seconds"}
    except Exception as e:
        return {"success": False, "project": project, "error": str(e)}




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
