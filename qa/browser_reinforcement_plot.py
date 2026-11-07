"""True-browser regression for the reinforcement Plotly chart.

Unlike streamlit.testing.AppTest, Chromium executes the JavaScript renderer.
This catches blank figure errors like "SyntaxError: Unexpected token '}'".
"""
from pathlib import Path
import subprocess
import sys
import time
import urllib.request

from playwright.sync_api import sync_playwright

PORT = 8765
URL = f"http://127.0.0.1:{PORT}"


def wait_for_server(proc, seconds=75):
    stop=time.monotonic()+seconds
    while time.monotonic()<stop:
        if proc.poll() is not None:
            raise RuntimeError(f"Streamlit process exited with {proc.returncode}")
        try:
            with urllib.request.urlopen(URL + "/_stcore/health", timeout=2) as r:
                if r.status==200:
                    return
        except Exception:
            time.sleep(0.5)
    raise RuntimeError("Streamlit HTTP server was not ready")


def check(page, label):
    page.wait_for_timeout(1000)
    body=page.locator("body").inner_text(timeout=15000)
    if "SyntaxError" in body or "Unexpected token" in body:
        raise AssertionError(f"{label}: JavaScript renderer exception: "+body[-2500:])
    if page.locator(".js-plotly-plot").count()<1:
        raise AssertionError(f"{label}: no Plotly DOM node was rendered: "+body[-2500:])
    print(f"BROWSER_REBAR_OK: {label}",flush=True)


def main():
    with subprocess.Popen(
        [sys.executable,"-m","streamlit","run","streamlit_app.py",
         "--server.headless=true","--server.port",str(PORT),
         "--server.address","127.0.0.1","--browser.gatherUsageStats=false"],
        stdout=subprocess.DEVNULL,stderr=subprocess.STDOUT,
        cwd=Path(__file__).resolve().parents[1],
    ) as proc:
        try:
            wait_for_server(proc)
            with sync_playwright() as browser_tool:
                browser=browser_tool.chromium.launch(channel="chrome",headless=True,
                                                     args=["--no-sandbox"])
                page=browser.new_page(viewport={"width":1480,"height":950})
                errors=[]
                page.on("pageerror",lambda e: errors.append(str(e)))
                page.goto(URL,wait_until="domcontentloaded",timeout=60000)
                sidebar=page.locator('[data-testid="stSidebar"]')
                sidebar.get_by_text("К1",exact=True).first.dispatch_event("click",timeout=45000)
                page.get_by_text("Схема арматуры",exact=True).wait_for(timeout=45000)
                try:
                    page.locator(".js-plotly-plot").first.wait_for(timeout=25000)
                    check(page,"both options on")
                    dims=page.get_by_role("checkbox",name="Показывать размерные цепочки")
                    labels=page.get_by_role("checkbox",name="Номера и диаметры стержней")
                    dims.uncheck()
                    check(page,"dimensions off")
                    labels.uncheck()
                    check(page,"both off")
                    dims.check()
                    check(page,"dimensions on, labels off")
                    labels.check()
                    check(page,"both back on")
                    if any("SyntaxError" in e or "Unexpected token" in e for e in errors):
                        raise AssertionError("JavaScript page errors: "+str(errors))
                except Exception:
                    print("BROWSER_JS_ERRORS:",errors,flush=True)
                    print("BROWSER_BODY:",page.locator("body").inner_text()[-5000:],flush=True)
                    page.screenshot(path="rebar_browser_failure.png",full_page=True)
                    raise
                finally:
                    browser.close()
        finally:
            proc.terminate()
            try:proc.wait(timeout=8)
            except subprocess.TimeoutExpired:proc.kill()


if __name__=="__main__":
    main()
