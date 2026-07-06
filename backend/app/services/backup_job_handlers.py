"""P1.9 — Backup & restore queue job handlers."""
from __future__ import annotations

from app.services.job_handlers import JobHandlerDef
from app.services.job_context import JobContext


async def _handle_backup_create(ctx: JobContext, payload: dict, job_meta: dict) -> dict:
    from app.db.session import get_sessionmaker
    from app.services.backup_orchestration import backup_service

    scope = payload.get("scope", "full")
    tenant_id = payload.get("tenant_id", "")
    encrypt = payload.get("encrypt", None)

    await ctx.set_progress(5, "preparing")
    ctx.check_cancelled()

    maker = get_sessionmaker()
    async with maker() as db:
        run = await backup_service.create(db, tenant_id=tenant_id, scope=scope,
                                           encrypt=encrypt,
                                           created_by=job_meta.get("created_by", "system"))
        ctx.check_cancelled()

        status = run.get("status", "failed")
        if status == "succeeded":
            await ctx.set_progress(100, "completed")
        else:
            raise RuntimeError(f"Backup status: {status}")
        return {"backup_id": run["id"], "status": status, "encrypted": run.get("encrypted"),
                "item_count": run.get("item_count"), "size_bytes": run.get("total_size_bytes")}


async def _handle_backup_verify(ctx: JobContext, payload: dict, job_meta: dict) -> dict:
    from app.db.session import get_sessionmaker
    from app.services.backup_orchestration import backup_service

    backup_id = payload.get("backup_id", "").strip()
    await ctx.set_progress(10, "verifying")
    ctx.check_cancelled()

    maker = get_sessionmaker()
    async with maker() as db:
        result = await backup_service.verify(db, backup_id)
        await ctx.set_progress(100, "completed")
        return result


async def _handle_backup_prune(ctx: JobContext, payload: dict, job_meta: dict) -> dict:
    from app.db.session import get_sessionmaker
    from app.services.backup_orchestration import backup_service

    dry_run = payload.get("dry_run", True)
    await ctx.set_progress(10, "scanning")
    ctx.check_cancelled()

    maker = get_sessionmaker()
    async with maker() as db:
        result = await backup_service.prune(db, dry_run=dry_run)
        await ctx.set_progress(100, "completed")
        return result


async def _handle_restore_validate(ctx: JobContext, payload: dict, job_meta: dict) -> dict:
    from app.db.session import get_sessionmaker
    from app.services.restore_service import restore_service

    backup_id = payload.get("backup_id", "").strip()
    target = payload.get("target", "test")
    await ctx.set_progress(10, "validating")
    ctx.check_cancelled()

    maker = get_sessionmaker()
    async with maker() as db:
        result = await restore_service.validate(db, backup_id, target)
        await ctx.set_progress(100, "completed")
        return result


async def _handle_restore_execute(ctx: JobContext, payload: dict, job_meta: dict) -> dict:
    from app.db.session import get_sessionmaker
    from app.services.restore_service import restore_service

    backup_id = payload.get("backup_id", "").strip()
    target = payload.get("target", "test")
    dry_run = payload.get("dry_run", False)
    validation_only = payload.get("validation_only", False)

    await ctx.set_progress(5, "preparing")
    ctx.check_cancelled()

    maker = get_sessionmaker()
    async with maker() as db:
        result = await restore_service.execute(
            db, backup_id, target=target, dry_run=dry_run,
            validation_only=validation_only,
            initiated_by=job_meta.get("created_by", "system"),
        )
        await ctx.set_progress(100, "completed")
        return {"restore_id": result["id"], "status": result["status"],
                "restored": result.get("restored_item_count", 0)}
