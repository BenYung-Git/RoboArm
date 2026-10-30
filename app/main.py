import json
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

from app.services.attachment_paths_service import AttachmentPathsService
from app.services.attachment_service import AttachmentService
from app.services.cad_model_service import CadModelService
from app.services.equipment_connection_service import EquipmentConnectionService
from app.services.maint_service import MaintService
from app.services.software_info_service import SoftwareInfoService
from app.services.table_layout_service import TableLayoutService
from app.services.ui_service import UiService
from app.services.virtual_demo_service import VirtualDemoService
from app.services.workflow_runner_service import WorkflowRunnerService

BASE_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"

ui_service = UiService()
attachment_paths_service = AttachmentPathsService(ui_service)
attachment_service = AttachmentService(ui_service, attachment_paths_service)
maint_service = MaintService(ui_service, attachment_service)
table_layout_service = TableLayoutService(ui_service, maint_service)
virtual_demo_service = VirtualDemoService(ui_service)
workflow_runner_service = WorkflowRunnerService(ui_service, virtual_demo_service)
software_info_service = SoftwareInfoService(ui_service)
cad_model_service = CadModelService(ui_service, attachment_paths_service)
equipment_connection_service = EquipmentConnectionService(ui_service)
app = FastAPI(title=ui_service.config["app_name"])
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


class PrefsUpdate(BaseModel):
    language: str = Field(...)
    font: str = Field(...)
    font_size: int = Field(...)


class AttachmentPathsPayload(BaseModel):
    model_root_windows: str | None = None
    model_root_linux: str | None = None


class AttachmentBrowsePayload(BaseModel):
    path: str | None = None


class AttachmentFileBrowsePayload(BaseModel):
    relative_dir: str | None = None


class MaintRowPayload(BaseModel):
    data: dict[str, Any] = Field(...)


class MoveJPayload(BaseModel):
    joints: list[Any] | None = None


class IoPayload(BaseModel):
    pin: int = Field(...)
    value: bool = Field(...)


class EquipmentConnectionPayload(BaseModel):
    driver_type: str = Field(...)
    connection_mode: str = Field(...)
    host_address: str = Field(...)
    remark: str | None = None


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


class TableLayoutPayload(BaseModel):
    zebra_enabled: bool = Field(...)
    zebra_color: str = Field(...)
    columns: list[dict[str, Any]] = Field(...)




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


@app.get("/api/system/software-info")
def system_software_info() -> JSONResponse:
    """Read-only host / app info. Does not load JAKA SDK or start robot processes."""
    try:
        return JSONResponse(software_info_service.build_payload())
    except (ValueError, FileNotFoundError, KeyError, RuntimeError) as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/api/system/attachment-paths")
def system_attachment_paths_get() -> JSONResponse:
    """Read attachment path settings and current server OS selection."""
    try:
        return JSONResponse(attachment_paths_service.build_payload())
    except (ValueError, FileNotFoundError, KeyError, RuntimeError) as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.put("/api/system/attachment-paths")
def system_attachment_paths_put(body: AttachmentPathsPayload) -> JSONResponse:
    """Save Windows/Linux model library roots after validation."""
    try:
        result = attachment_paths_service.save_settings(
            body.model_root_windows,
            body.model_root_linux,
        )
        payload = attachment_paths_service.build_payload()
        payload["validation_status"] = result["validation_status"]
        payload["validation_message"] = result["validation_message"]
        payload["windows_path"] = result["windows_path"]
        payload["linux_path"] = result["linux_path"]
        payload["effective_path"] = result["effective_path"]
        payload["windows_validation"] = result["windows_validation"]
        payload["linux_validation"] = result["linux_validation"]
        payload["saved"] = True
        return JSONResponse(payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except (FileNotFoundError, KeyError, RuntimeError) as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/api/system/attachment-paths/validate")
def system_attachment_paths_validate(body: AttachmentPathsPayload) -> JSONResponse:
    """Validate paths without modifying saved settings."""
    try:
        return JSONResponse(
            attachment_paths_service.validate_settings_input(
                body.model_root_windows,
                body.model_root_linux,
            )
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except (FileNotFoundError, KeyError, RuntimeError) as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/api/system/attachment-paths/browse")
def system_attachment_paths_browse(body: AttachmentBrowsePayload) -> JSONResponse:
    """List subfolders within deploy-configured browse roots (server-side only)."""
    try:
        return JSONResponse(attachment_paths_service.browse(body.path))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except (FileNotFoundError, KeyError, RuntimeError) as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/api/equipment/{equipment_txid}/connection")
def equipment_connection_get(equipment_txid: int) -> JSONResponse:
    """Read equipment connection settings. Does not load SDK or connect."""
    try:
        return JSONResponse(equipment_connection_service.build_view(equipment_txid))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (ValueError, FileNotFoundError, RuntimeError) as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.put("/api/equipment/{equipment_txid}/connection")
def equipment_connection_put(
    equipment_txid: int, body: EquipmentConnectionPayload
) -> JSONResponse:
    """Save equipment connection settings only. Does not connect or load SDK."""
    try:
        return JSONResponse(
            equipment_connection_service.save_connection(
                equipment_txid,
                {
                    "driver_type": body.driver_type,
                    "connection_mode": body.connection_mode,
                    "host_address": body.host_address,
                    "remark": body.remark,
                },
            )
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        code = str(exc)
        view = None
        try:
            view = equipment_connection_service.build_view(equipment_txid)
        except Exception:
            view = None
        detail = code
        if view and code in view.get("errors", {}):
            detail = view["errors"][code]
        raise HTTPException(status_code=400, detail=detail) from exc
    except (FileNotFoundError, RuntimeError) as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.delete("/api/equipment/{equipment_txid}/connection")
def equipment_connection_delete(equipment_txid: int) -> JSONResponse:
    """Clear equipment connection settings. Does not delete inventory or combo items."""
    try:
        return JSONResponse(
            equipment_connection_service.clear_connection(equipment_txid)
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        code = str(exc)
        detail = code
        try:
            view = equipment_connection_service.build_view(equipment_txid)
            if code in view.get("errors", {}):
                detail = view["errors"][code]
        except Exception:
            pass
        raise HTTPException(status_code=400, detail=detail) from exc
    except (FileNotFoundError, RuntimeError) as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/api/maint/{table_key}/meta")
def maint_meta(table_key: str) -> JSONResponse:
    try:
        return JSONResponse(maint_service.build_meta(table_key))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (ValueError, FileNotFoundError, RuntimeError) as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/api/table-ui/{table_key}/meta")
def table_ui_meta(table_key: str) -> JSONResponse:
    try:
        return JSONResponse(maint_service.build_table_ui_meta(table_key))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (ValueError, FileNotFoundError, RuntimeError) as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/api/table-ui/{table_key}/next-txid")
def table_ui_next_txid(table_key: str) -> JSONResponse:
    try:
        return JSONResponse({"next_txid": maint_service.peek_next_txid(table_key)})
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (ValueError, FileNotFoundError, RuntimeError) as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/api/table-ui/{table_key}/peek-auto/{field}")
def table_ui_peek_auto(table_key: str, field: str, scope_value: str) -> JSONResponse:
    try:
        return JSONResponse(
            {
                "field": field,
                "value": maint_service.peek_auto_gen_value(
                    table_key, field, scope_value
                ),
            }
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except (FileNotFoundError, RuntimeError) as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/api/table-ui/{table_key}/layout")
def table_ui_get_layout(table_key: str) -> JSONResponse:
    try:
        return JSONResponse(table_layout_service.ensure_table_layout(table_key))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (ValueError, FileNotFoundError, RuntimeError) as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.put("/api/table-ui/{table_key}/layout")
def table_ui_save_layout(table_key: str, body: TableLayoutPayload) -> JSONResponse:
    try:
        return JSONResponse(
            table_layout_service.save_layout(
                table_key,
                {
                    "zebra_enabled": body.zebra_enabled,
                    "zebra_color": body.zebra_color,
                    "columns": body.columns,
                },
            )
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except (FileNotFoundError, RuntimeError) as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/api/table-ui/{table_key}/rows")
def table_ui_list_rows(
    table_key: str,
    search: str = "",
    isDisable: str = "",
    sort: str = "",
    filter_field: str = "",
    filter_value: str = "",
) -> JSONResponse:
    try:
        layout = table_layout_service.ensure_table_layout(table_key)
        table_def = maint_service.get_table_def(table_key)
        flag_fields = {column["field"] for column in table_def["columns"] if column["is_flag"]}
        search_fields = [
            field
            for field in layout["list_fields"]
            if field not in flag_fields
            and next(
                (
                    col
                    for col in table_def["columns"]
                    if col["field"] == field
                    and col.get("db_persist", True) is not False
                    and col["field_type"] != "display"
                ),
                None,
            )
            is not None
        ]
        sort_specs: list[dict[str, str]] | None
        if sort == "":
            sort_specs = []
            for column in layout["columns"]:
                if column.get("is_system"):
                    continue
                direction = column.get("sort_direction") or ""
                if direction in ("asc", "desc"):
                    sort_specs.append(
                        {"field": column["field_key"], "dir": direction}
                    )
        else:
            parsed = json.loads(sort)
            if not isinstance(parsed, list):
                raise ValueError("Invalid sort payload")
            sort_specs = []
            for item in parsed:
                if not isinstance(item, dict):
                    raise ValueError("Invalid sort item")
                if "field" not in item or "dir" not in item:
                    raise ValueError("Invalid sort item")
                sort_specs.append({"field": str(item["field"]), "dir": str(item["dir"])})
        eq_filters: dict[str, Any] | None = None
        if filter_field != "" or filter_value != "":
            if filter_field == "" or filter_value == "":
                raise ValueError("filter_field and filter_value must both be set")
            eq_filters = {filter_field: filter_value}
        rows = maint_service.list_rows(
            table_key,
            search=search if search != "" else None,
            flag_filters={"isDisable": isDisable},
            search_fields=search_fields,
            sort_specs=sort_specs,
            eq_filters=eq_filters,
        )
        return JSONResponse({"rows": rows, "layout": layout})
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail="Invalid sort payload") from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except (FileNotFoundError, RuntimeError) as exc:
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


class WorkflowRunStartPayload(BaseModel):
    workflow_txid: int = Field(...)


class WorkflowAnimationAckPayload(BaseModel):
    run_txid: int = Field(...)
    step_txid: int = Field(...)
    seq: int = Field(...)
    ok: bool = Field(...)
    error: str | None = None


@app.get("/api/workflow-runs/status")
def workflow_run_status(run_txid: int | None = None) -> JSONResponse:
    try:
        return JSONResponse(workflow_runner_service.get_status(run_txid=run_txid))
    except (ValueError, FileNotFoundError, KeyError, RuntimeError) as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/api/workflow-runs/start")
def workflow_run_start(body: WorkflowRunStartPayload) -> JSONResponse:
    try:
        return JSONResponse(workflow_runner_service.start(body.workflow_txid))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except (FileNotFoundError, RuntimeError) as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/api/workflow-runs/stop")
def workflow_run_stop() -> JSONResponse:
    try:
        return JSONResponse(workflow_runner_service.stop())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except (FileNotFoundError, RuntimeError) as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/api/workflow-runs/reset")
def workflow_run_reset() -> JSONResponse:
    try:
        return JSONResponse(workflow_runner_service.reset())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except (FileNotFoundError, RuntimeError) as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/api/workflow-runs/animation-ack")
def workflow_run_animation_ack(body: WorkflowAnimationAckPayload) -> JSONResponse:
    try:
        return JSONResponse(
            workflow_runner_service.animation_ack(
                run_txid=body.run_txid,
                step_txid=body.step_txid,
                seq=body.seq,
                ok=body.ok,
                error=body.error,
            )
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except (FileNotFoundError, RuntimeError) as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/api/inventory/{inventory_id}/attachments/active")
def inventory_attachments_active(inventory_id: int) -> JSONResponse:
    """List enabled attachments for one inventory row (preview dropdown)."""
    try:
        return JSONResponse(
            {"items": attachment_service.list_active_for_inventory(inventory_id)}
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/inventory/attachments/browse-files")
def inventory_attachments_browse_files(
    body: AttachmentFileBrowsePayload,
) -> JSONResponse:
    """List directories and files under the configured attachment root only."""
    try:
        return JSONResponse(attachment_service.browse_files(body.relative_dir))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except (FileNotFoundError, PermissionError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/inventory/{inventory_id}/attachments/{txid}/preview")
def inventory_attachment_preview(inventory_id: int, txid: int) -> JSONResponse:
    try:
        return JSONResponse(
            attachment_service.build_preview_meta(inventory_id, txid)
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/inventory/{inventory_id}/attachments/{txid}/text")
def inventory_attachment_text(inventory_id: int, txid: int) -> JSONResponse:
    try:
        return JSONResponse(
            attachment_service.read_text_preview(inventory_id, txid)
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/inventory/{inventory_id}/attachments/{txid}/content")
def inventory_attachment_content(
    inventory_id: int, txid: int, disposition: str = "inline"
) -> FileResponse:
    """Serve registered attachment content (no arbitrary path input)."""
    try:
        path, row = attachment_service.resolve_content_path(inventory_id, txid)
        type_name = str(row.get("Type") or "").lower()
        media = attachment_service.content_type_for(str(row.get("File") or ""), type_name)
        filename = attachment_service.safe_download_name(str(row.get("File") or ""))
        disp = "attachment" if disposition == "attachment" else "inline"
        return FileResponse(
            path,
            media_type=media,
            filename=filename,
            headers={
                "Cache-Control": "no-store",
                "Content-Disposition": f'{disp}; filename="{filename}"',
                "X-Content-Type-Options": "nosniff",
            },
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/cad-models/{model_key}/assembly.glb")
def cad_model_assembly_glb(model_key: str) -> FileResponse:
    """Serve one allowlisted CAD GLB under the attachment-paths model root."""
    try:
        path = cad_model_service.resolve_glb(model_key)
        return FileResponse(
            path,
            media_type="model/gltf-binary",
            filename=path.name,
            headers={"Cache-Control": "no-store"},
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/cad-models/{model_key}/meta")
def cad_model_meta(model_key: str) -> JSONResponse:
    try:
        meta = cad_model_service.build_viewer_cad_static(model_key)
        if meta is None:
            raise HTTPException(status_code=404, detail="Unknown CAD model_key")
        return JSONResponse(meta)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except (FileNotFoundError, KeyError, RuntimeError) as exc:
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

