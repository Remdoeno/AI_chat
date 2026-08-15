# Shared-user credentials and analysis-mode authorization.


def shared_user_id_for_device(device_id: str) -> str:
    normalized_device = normalize_visitor_ip(device_id)
    if not normalized_device or not is_device_identity(normalized_device):
        return ""
    with connect_db() as conn:
        scope = binding_scope_for_device(conn, normalized_device)
    return clean_shared_user_id(str(scope.get("shared_user_id") or ""))


def shared_user_device_ids(shared_user_id: str) -> List[str]:
    normalized_user = clean_shared_user_id(shared_user_id)
    if not normalized_user:
        return []
    with connect_db() as conn:
        rows = conn.execute(
            """
            SELECT device_id
            FROM shared_user_bindings
            WHERE shared_user_id = ?
            ORDER BY updated_at DESC, device_id ASC
            """,
            (normalized_user,),
        ).fetchall()
    return [
        normalize_visitor_ip(str(row["device_id"] or ""))
        for row in rows
        if is_device_identity(str(row["device_id"] or ""))
    ]


def require_shared_user_for_request(request: Request) -> str:
    shared_user_id = shared_user_id_for_device(visitor_ip(request))
    if not shared_user_id:
        raise HTTPException(status_code=409, detail="shared user binding required")
    return shared_user_id


def shared_user_owns_session(shared_user_id: str, session_id: str) -> bool:
    normalized_user = clean_shared_user_id(shared_user_id)
    if not normalized_user or not str(session_id or "").strip():
        return False
    devices = shared_user_device_ids(normalized_user)
    if not devices:
        return False
    in_clause, params = sql_in_clause_params(devices)
    with connect_db() as conn:
        row = conn.execute(
            f"SELECT 1 FROM sessions WHERE id = ? AND visitor_ip IN {in_clause} LIMIT 1",
            (str(session_id), *params),
        ).fetchone()
    return row is not None


def require_shared_user_session(request: Request, session_id: str) -> str:
    shared_user_id = require_shared_user_for_request(request)
    if not shared_user_owns_session(shared_user_id, session_id):
        raise HTTPException(status_code=404, detail="session not found")
    return shared_user_id


def shared_user_host_device_id(shared_user_id: str) -> str:
    normalized_user = clean_shared_user_id(shared_user_id)
    if not normalized_user:
        return ""
    with connect_db() as conn:
        return effective_host_device_id(conn, normalized_user)


def shared_user_memory_device_id(shared_user_id: str, requested_device_id: str = "") -> str:
    devices = shared_user_device_ids(shared_user_id)
    if not devices:
        raise HTTPException(status_code=409, detail="shared user has no bound device")
    requested = normalize_visitor_ip(requested_device_id) if str(requested_device_id or "").strip() else ""
    if requested:
        if requested not in devices:
            raise HTTPException(status_code=403, detail="memory device is outside shared user scope")
        return requested
    host = shared_user_host_device_id(shared_user_id)
    return host if host in devices else devices[0]


def shared_user_credential(shared_user_id: str) -> Optional[Dict[str, object]]:
    normalized_user = clean_shared_user_id(shared_user_id)
    if not normalized_user:
        return None
    with connect_db() as conn:
        row = conn.execute(
            """
            SELECT shared_user_id, algorithm, iterations, salt, password_hash,
                   created_at, updated_at
            FROM shared_user_credentials
            WHERE shared_user_id = ?
            LIMIT 1
            """,
            (normalized_user,),
        ).fetchone()
    return row_to_dict(row)


def has_shared_user_password(shared_user_id: str) -> bool:
    return shared_user_credential(shared_user_id) is not None


def hash_shared_user_password(password: str, salt_hex: str = "") -> Dict[str, object]:
    text = str(password or "")
    if len(text) < 6:
        raise HTTPException(status_code=400, detail="password must be at least 6 characters")
    try:
        salt = bytes.fromhex(salt_hex) if salt_hex else secrets.token_bytes(16)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="invalid password salt") from exc
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        text.encode("utf-8"),
        salt,
        AUTH_PBKDF2_ITERATIONS,
    )
    return {
        "algorithm": "pbkdf2_sha256",
        "iterations": AUTH_PBKDF2_ITERATIONS,
        "salt": salt.hex(),
        "password_hash": digest.hex(),
    }


def save_shared_user_password(shared_user_id: str, password: str) -> Dict[str, object]:
    normalized_user = clean_shared_user_id(shared_user_id)
    if not normalized_user:
        raise HTTPException(status_code=409, detail="shared user binding required")
    config = hash_shared_user_password(password)
    now = utc_now()
    with connect_db() as conn:
        conn.execute(
            """
            INSERT INTO shared_user_credentials (
                shared_user_id, algorithm, iterations, salt, password_hash,
                created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(shared_user_id) DO UPDATE SET
                algorithm = excluded.algorithm,
                iterations = excluded.iterations,
                salt = excluded.salt,
                password_hash = excluded.password_hash,
                updated_at = excluded.updated_at
            """,
            (
                normalized_user,
                config["algorithm"],
                config["iterations"],
                config["salt"],
                config["password_hash"],
                now,
                now,
            ),
        )
    return {"shared_user_id": normalized_user, "updated_at": now}


def verify_shared_user_password(shared_user_id: str, password: str) -> bool:
    config = shared_user_credential(shared_user_id)
    if not config:
        return False
    try:
        iterations = int(config.get("iterations") or AUTH_PBKDF2_ITERATIONS)
        salt = bytes.fromhex(str(config.get("salt") or ""))
        expected = str(config.get("password_hash") or "")
        actual = hashlib.pbkdf2_hmac(
            "sha256",
            str(password or "").encode("utf-8"),
            salt,
            iterations,
        ).hex()
        return bool(expected) and hmac.compare_digest(actual, expected)
    except Exception:
        return False


def initialize_or_verify_shared_user_password(
    shared_user_id: str,
    password: str,
    confirm_password: str = "",
) -> bool:
    normalized_user = clean_shared_user_id(shared_user_id)
    if not normalized_user:
        raise HTTPException(status_code=409, detail="shared user binding required")
    if has_shared_user_password(normalized_user):
        if not verify_shared_user_password(normalized_user, password):
            raise HTTPException(status_code=401, detail="shared user password is invalid")
        return False
    if str(password or "") != str(confirm_password or ""):
        raise HTTPException(status_code=400, detail="password confirmation does not match")
    save_shared_user_password(normalized_user, password)
    return True


def authorize_user_memory_binding_change(
    current_device_id: str,
    target_shared_user_id: str,
    password: str,
    confirm_password: str = "",
) -> Dict[str, object]:
    current_device = normalize_visitor_ip(current_device_id)
    if not current_device or not is_device_identity(current_device):
        raise HTTPException(status_code=400, detail="device identity required")
    current_user = shared_user_id_for_device(current_device)
    target_user = clean_shared_user_id(target_shared_user_id)
    authorization_user = target_user or current_user
    if not authorization_user:
        raise HTTPException(status_code=400, detail="shared user id is required")
    initialized = initialize_or_verify_shared_user_password(
        authorization_user,
        password,
        confirm_password,
    )
    return {
        "shared_user_id": authorization_user,
        "password_initialized": initialized,
        "switching_user": bool(current_user and target_user and current_user != target_user),
    }


def encode_analysis_scope(shared_user_id: str) -> str:
    encoded = base64.urlsafe_b64encode(shared_user_id.encode("utf-8")).decode("ascii")
    return encoded.rstrip("=")


def decode_analysis_scope(value: str) -> str:
    text = str(value or "")
    if not text:
        return ""
    try:
        padded = text + "=" * (-len(text) % 4)
        return clean_shared_user_id(base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8"))
    except Exception:
        return ""


def shared_user_secret_material(shared_user_id: str) -> str:
    config = shared_user_credential(shared_user_id)
    if not config:
        return ""
    return f"{config.get('salt', '')}:{config.get('password_hash', '')}"


def analysis_auth_token(shared_user_id: str) -> str:
    normalized_user = clean_shared_user_id(shared_user_id)
    secret_material = shared_user_secret_material(normalized_user)
    if not normalized_user or not secret_material:
        return ""
    scope = encode_analysis_scope(normalized_user)
    signature = hmac.new(
        secret_material.encode("utf-8"),
        f"wangcai-analysis-user:{normalized_user}".encode("utf-8"),
        "sha256",
    ).hexdigest()
    return f"v1.{scope}.{signature}"


def analysis_cookie_shared_user(request: Request) -> str:
    token = str(request.cookies.get(ANALYSIS_COOKIE_NAME, "") or "")
    parts = token.split(".")
    if len(parts) != 3 or parts[0] != "v1":
        return ""
    shared_user_id = decode_analysis_scope(parts[1])
    expected = analysis_auth_token(shared_user_id)
    if not expected or not hmac.compare_digest(token, expected):
        return ""
    return shared_user_id


def is_analysis_authenticated(request: Request, enforce_device_scope: bool = False) -> bool:
    token_user = analysis_cookie_shared_user(request)
    if not token_user:
        return False
    if not enforce_device_scope:
        return True
    device_user = shared_user_id_for_device(visitor_ip(request))
    return bool(device_user) and hmac.compare_digest(token_user, device_user)


def require_analysis_user(request: Request) -> str:
    if not is_analysis_authenticated(request, enforce_device_scope=True):
        raise HTTPException(status_code=401, detail="shared user analysis password required")
    return analysis_cookie_shared_user(request)


def analysis_auth_status(request: Request) -> Dict[str, object]:
    device_id = visitor_ip(request)
    shared_user_id = shared_user_id_for_device(device_id)
    return {
        "bound": bool(shared_user_id),
        "shared_user_id": shared_user_id,
        "configured": has_shared_user_password(shared_user_id) if shared_user_id else False,
        "authenticated": is_analysis_authenticated(request, enforce_device_scope=True),
    }
