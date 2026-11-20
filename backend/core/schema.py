"""Shared OpenAPI error contracts, without changing runtime response bodies."""


def document_errors(result, generator, request, public):
    schemas = result.setdefault("components", {}).setdefault("schemas", {})
    schemas["ApiError"] = {
        "type": "object",
        "required": ["detail"],
        "properties": {"detail": {"type": "string"}},
    }
    schemas["ValidationErrors"] = {
        "type": "object",
        "additionalProperties": {},
        "description": "Ошибки по именам полей. Вложенные формы возвращают объекты и списки; общие ошибки — non_field_errors.",
    }
    descriptions = {
        "400": "Ошибка входных данных. См. поля формы или detail.",
        "401": "Нужен действующий access-токен; для refresh — действующий refresh-токен.",
        "403": "Недостаточно прав или действие запрещено состоянием опроса.",
        "404": "Объект не найден.",
        "409": "Конфликт, например занятый никнейм или запрещённое перепрохождение.",
        "415": "Неверный Content-Type. JSON для API, multipart/form-data для аватара.",
        "429": "Слишком много запросов. Повторите после Retry-After секунд.",
    }
    for path, item in result.get("paths", {}).items():
        if not path.startswith("/api/") or path in {"/api/health", "/api/schema"}:
            continue
        for method, operation in item.items():
            if method not in {"get", "post", "patch", "delete"}:
                continue
            responses = operation.setdefault("responses", {})
            for code, description in descriptions.items():
                schema = {"$ref": "#/components/schemas/ApiError"}
                if code == "400":
                    schema = {"anyOf": [schema, {"$ref": "#/components/schemas/ValidationErrors"}]}
                responses.setdefault(
                    code, {"description": description, "content": {"application/json": {"schema": schema}}}
                )
    return result
