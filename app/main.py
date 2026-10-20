from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

from app.services.maint_service import MaintService
from app.services.ui_service import UiService
from app.services.virtual_demo_service import VirtualDemoService

BASE_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"

ui_service = UiService()
maint_service = MaintService(ui_service)
virtual_demo_service = VirtualDemoService(ui_service)
app = FastAPI(title=ui_service.config["app_name"])
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


class PrefsUpdate(BaseModel):
    language: str = Field(...)
    font: str = Field(...)
    font_size: int = Field(...)


class MaintRowPayload(BaseModel):
    data: dict[str, Any] = Field(...)


class MoveJPayload(BaseModel):
    joints: list[Any] | None = None


class IoPayload(BaseModel):
    pin: int = Field(...)
    value: bool = Field(...)


class NotImplementedPayload(BaseModel):
    action_key: str = Field(...)


class ModelSelectPayload(BaseModel):
    model_key: str = Field(...)


class JointsPayload(BaseModel):
    joints: list[Any] = Field(...)


class DemoSelectPayload(BaseModel):
    demo_key: str | None = None


class DemoRuntimePayload(BaseModel):
    phase: str | None = None
    grasped: bool | None = None
    gap_m: float | None = None
    object_pose: dict[str, Any] | None = None
    completed: bool | None = None
    aborted: bool | None = None


class DemoMoveJPayload(BaseModel):
    joints: list[Any] = Field(...)


class DemoPreflightPayload(BaseModel):
    ok: bool = Field(...)
    detail: str | None = None


class CompleteMotionPayload(BaseModel):
    motion_id: int | None = None




def render_menu_page(request: Request, menu_key: str) -> HTMLResponse:
    try:
        context = ui_service.build_page_context(menu_key)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (ValueError, FileNotFoundError, RuntimeError) as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return templates.TemplateResponse(request, "page.html", context)


@app.get("/", response_class=RedirectResponse)
def root() -> RedirectResponse:
    menus = ui_service.get_menus()
    if not menus:
        raise HTTPException(status_code=500, detail="menus table is empty")
    return RedirectResponse(url=menus[0]["route_path"], status_code=302)


@app.get("/page/{menu_key}", response_class=HTMLResponse)
def page(request: Request, menu_key: str) -> HTMLResponse:
    return render_menu_page(request, menu_key)


@app.get("/api/prefs")
def get_prefs() -> JSONResponse:
    try:
        return JSONResponse(ui_service.get_prefs())
    except (ValueError, FileNotFoundError, KeyError, RuntimeError) as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/api/prefs")
def post_prefs(body: PrefsUpdate) -> JSONResponse:
    try:
        prefs = ui_service.save_prefs(body.language, body.font, body.font_size)
        return JSONResponse(prefs)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except (FileNotFoundError, KeyError, RuntimeError) as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/api/maint/{table_key}/meta")
def maint_meta(table_key: str) -> JSONResponse:
    try:
        return JSONResponse(maint_service.build_meta(table_key))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (ValueError, FileNotFoundError, RuntimeError) as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/api/maint/{table_key}/rows")
def maint_list_rows(
    table_key: str,
    search: str = "",
    isDisable: str = "",
) -> JSONResponse:
    try:
        rows = maint_service.list_rows(
            table_key,
            search=search if search != "" else None,
            flag_filters={"isDisable": isDisable},
        )
        return JSONResponse({"rows": rows})
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except (FileNotFoundError, RuntimeError) as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/api/maint/{table_key}/rows/{txid}")
def maint_get_row(table_key: str, txid: int) -> JSONResponse:
    try:
        row = maint_service.get_row(table_key, txid)
        if row is None:
            raise KeyError(f"Row not found: TxId={txid}")
        return JSONResponse(row)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except (FileNotFoundError, RuntimeError) as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/api/maint/{table_key}/rows")
def maint_create_row(table_key: str, body: MaintRowPayload) -> JSONResponse:
    try:
        row = maint_service.create_row(table_key, body.data)
        return JSONResponse(row)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except (FileNotFoundError, RuntimeError) as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.put("/api/maint/{table_key}/rows/{txid}")
def maint_update_row(
    table_key: str, txid: int, body: MaintRowPayload
) -> JSONResponse:
    try:
        row = maint_service.update_row(table_key, txid, body.data)
        return JSONResponse(row)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except (FileNotFoundError, RuntimeError) as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/api/maint/{table_key}/rows/{txid}/toggle-disable")
def maint_toggle_disable(table_key: str, txid: int) -> JSONResponse:
    try:
        row = maint_service.toggle_disable(table_key, txid)
        return JSONResponse(row)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except (FileNotFoundError, RuntimeError) as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/api/virtual-demo/state")
def virtual_demo_state() -> JSONResponse:
    try:
        return JSONResponse(virtual_demo_service.get_snapshot())
    except (ValueError, FileNotFoundError, KeyError, RuntimeError) as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/api/virtual-demo/connect")
def virtual_demo_connect() -> JSONResponse:
    return JSONResponse(virtual_demo_service.connect())


@app.post("/api/virtual-demo/disconnect")
def virtual_demo_disconnect() -> JSONResponse:
    return JSONResponse(virtual_demo_service.disconnect())


@app.post("/api/virtual-demo/estop")
def virtual_demo_estop() -> JSONResponse:
    return JSONResponse(virtual_demo_service.emergency_stop())


@app.post("/api/virtual-demo/reset-estop")
def virtual_demo_reset_estop() -> JSONResponse:
    return JSONResponse(virtual_demo_service.reset_estop())


@app.post("/api/virtual-demo/move-home")
def virtual_demo_move_home() -> JSONResponse:
    return JSONResponse(virtual_demo_service.move_to_home())


@app.post("/api/virtual-demo/move-j")
def virtual_demo_move_j(body: MoveJPayload) -> JSONResponse:
    return JSONResponse(virtual_demo_service.move_j(body.joints))


@app.post("/api/virtual-demo/select-demo")
def virtual_demo_select_demo(body: DemoSelectPayload) -> JSONResponse:
    try:
        return JSONResponse(virtual_demo_service.select_demo(body.demo_key))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/api/virtual-demo/demo/start")
def virtual_demo_demo_start() -> JSONResponse:
    try:
        return JSONResponse(virtual_demo_service.start_demo())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/virtual-demo/demo/reset")
def virtual_demo_demo_reset() -> JSONResponse:
    return JSONResponse(virtual_demo_service.reset_demo())


@app.post("/api/virtual-demo/demo/preflight")
def virtual_demo_demo_preflight(body: DemoPreflightPayload) -> JSONResponse:
    return JSONResponse(
        virtual_demo_service.mark_demo_preflight(body.ok, body.detail)
    )


@app.post("/api/virtual-demo/demo/runtime")
def virtual_demo_demo_runtime(body: DemoRuntimePayload) -> JSONResponse:
    payload = body.model_dump(exclude_none=True)
    return JSONResponse(virtual_demo_service.update_demo_runtime(payload))


@app.post("/api/virtual-demo/demo/move-j")
def virtual_demo_demo_move_j(body: DemoMoveJPayload) -> JSONResponse:
    return JSONResponse(
        virtual_demo_service.move_j(body.joints, allow_during_demo=True)
    )



@app.post("/api/virtual-demo/select-model")
def virtual_demo_select_model(body: ModelSelectPayload) -> JSONResponse:
    try:
        return JSONResponse(virtual_demo_service.select_model(body.model_key))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/api/virtual-demo/set-target")
def virtual_demo_set_target(body: JointsPayload) -> JSONResponse:
    return JSONResponse(virtual_demo_service.set_target_joints(body.joints))


@app.post("/api/virtual-demo/update-current")
def virtual_demo_update_current(body: JointsPayload) -> JSONResponse:
    return JSONResponse(virtual_demo_service.update_current_joints(body.joints))


@app.post("/api/virtual-demo/complete-motion")
def virtual_demo_complete_motion(
    body: CompleteMotionPayload = CompleteMotionPayload(),
) -> JSONResponse:
    return JSONResponse(virtual_demo_service.complete_motion(body.motion_id))


@app.post("/api/virtual-demo/abort-motion")
def virtual_demo_abort_motion() -> JSONResponse:
    return JSONResponse(virtual_demo_service.abort_motion())


@app.post("/api/virtual-demo/set-do")
def virtual_demo_set_do(body: IoPayload) -> JSONResponse:
    try:
        return JSONResponse(virtual_demo_service.set_do(body.pin, body.value))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/virtual-demo/set-di")
def virtual_demo_set_di(body: IoPayload) -> JSONResponse:
    try:
        return JSONResponse(virtual_demo_service.set_di(body.pin, body.value))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/virtual-demo/not-implemented")
def virtual_demo_not_implemented(body: NotImplementedPayload) -> JSONResponse:
    try:
        return JSONResponse(virtual_demo_service.not_implemented(body.action_key))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

