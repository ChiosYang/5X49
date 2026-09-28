from fastapi import APIRouter, HTTPException

from app.contracts.ask import AskQuestion, AskQueryRequest, AskResolveRequest
from app.services.ask import ASK_CONTRACT_VERSION, AskError, ask_service

router = APIRouter()


def _call(callback):
    try:
        return callback()
    except AskError as exc:
        raise HTTPException(exc.status, detail={"code": exc.code}) from None


@router.get("/ask/status")
def ask_status():
    return {"version": ASK_CONTRACT_VERSION, "configured": ask_service.interpreter.configured(),
            "read_only": True, "form_available": True}


@router.post("/ask/interpret")
def interpret_question(request: AskQuestion):
    return _call(lambda: ask_service.interpret(request))


@router.post("/ask/resolve")
def resolve_plan(request: AskResolveRequest):
    return _call(lambda: ask_service.resolve(request))


@router.post("/ask/query")
def query_plan(request: AskQueryRequest):
    return _call(lambda: ask_service.query(request))
