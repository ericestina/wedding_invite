# app.py — backend de RSVP para o site do casamento
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import sqlite3, datetime
from fastapi.responses import StreamingResponse

app = FastAPI(title="Wedding RSVP API")

# permite chamadas do seu domínio
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # depois restrinja para seu domínio
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# modelo de dados
class RSVP(BaseModel):
    name: str
    email: str
    attend: str
    msg: str | None = None

# cria tabela se não existir
def init_db():
    conn = sqlite3.connect("guests.db")
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS rsvp(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT,
            name TEXT,
            email TEXT,
            attend TEXT,
            msg TEXT
        )
    """)
    conn.commit()
    conn.close()

@app.on_event("startup")
def startup():
    init_db()

@app.post("/rsvp")
def save_rsvp(rsvp: RSVP):
    conn = sqlite3.connect("guests.db")
    c = conn.cursor()
    c.execute(
        "INSERT INTO rsvp(created_at,name,email,attend,msg) VALUES (?,?,?,?,?)",
        (datetime.datetime.now().isoformat(), rsvp.name, rsvp.email, rsvp.attend, rsvp.msg)
    )
    conn.commit(); conn.close()
    return {"ok": True, "message": "RSVP saved successfully"}

@app.get("/rsvp")
def list_rsvp():
    conn = sqlite3.connect("guests.db")
    c = conn.cursor()
    c.execute("SELECT created_at, name, email, attend, msg FROM rsvp ORDER BY created_at DESC")
    data = c.fetchall()
    conn.close()
    return {"count": len(data), "guests": data}

@app.get("/rsvp/export")
def export_csv():
    import csv, io
    conn = sqlite3.connect("guests.db")
    c = conn.cursor()
    c.execute("SELECT * FROM rsvp")
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([d[0] for d in c.description])  # cabeçalhos
    writer.writerows(c.fetchall())
    conn.close()
    output.seek(0)
    # faz o navegador baixar o arquivo
    return StreamingResponse(
        io.BytesIO(output.getvalue().encode("utf-8")),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=guests.csv"}
    )

# ====== IMPORTS NO TOPO (se ainda não tiver) ======
from fastapi.responses import HTMLResponse
import html

# ====== MINI DASHBOARD HTML: /rsvp/export/html ======
@app.get("/rsvp/export/html", response_class=HTMLResponse)
def export_html(
    q: str | None = None,              # busca por nome/email/mensagem
    attend: str | None = None,         # 'yes' | 'no'
    order: str = "created_at_desc",    # created_at_desc | created_at_asc | name_asc | name_desc
    page: int = 1,
    size: int = 25
):
    # normaliza parâmetros
    page = max(1, page)
    size = min(max(1, size), 200)

    # mapeia ordenação
    order_map = {
        "created_at_desc": "created_at DESC",
        "created_at_asc":  "created_at ASC",
        "name_asc":        "name ASC, created_at DESC",
        "name_desc":       "name DESC, created_at DESC",
    }
    order_sql = order_map.get(order, "created_at DESC")

    # filtros
    where = []
    params = []
    if q:
        where.append("(name LIKE ? OR email LIKE ? OR msg LIKE ?)")
        like = f"%{q}%"
        params.extend([like, like, like])
    if attend in ("yes", "no"):
        where.append("attend = ?")
        params.append(attend)

    where_sql = ("WHERE " + " AND ".join(where)) if where else ""

    # paginação
    offset = (page - 1) * size

    # consulta total
    conn = sqlite3.connect("guests.db")
    c = conn.cursor()
    c.execute(f"SELECT COUNT(*) FROM rsvp {where_sql}", params)
    total = c.fetchone()[0]

    # consulta dados
    c.execute(
        f"""SELECT id, created_at, name, email, attend, msg
            FROM rsvp
            {where_sql}
            ORDER BY {order_sql}
            LIMIT ? OFFSET ?""",
        params + [size, offset]
    )
    rows = c.fetchall()
    conn.close()

    # monta linhas HTML (escape para evitar XSS)
    def esc(x): return html.escape("" if x is None else str(x))
    tr_html = "\n".join(
        f"<tr>"
        f"<td>{esc(r[0])}</td>"
        f"<td>{esc(r[1])}</td>"
        f"<td>{esc(r[2])}</td>"
        f"<td><a href='mailto:{esc(r[3])}'>{esc(r[3])}</a></td>"
        f"<td>{'✅' if r[4]=='yes' else '❌'}</td>"
        f"<td>{esc(r[5])}</td>"
        f"</tr>"
        for r in rows
    )

    # navegação
    base = "/rsvp/export/html"
    def link(page):
        from urllib.parse import urlencode
        args = dict(page=page, size=size, order=order)
        if q: args["q"] = q
        if attend in ("yes","no"): args["attend"] = attend
        return f"{base}?{urlencode(args)}"

    prev_link = link(page-1) if page > 1 else None
    next_link = link(page+1) if page * size < total else None

    # opções de ordenação (selecionadas)
    def sel(x): return "selected" if order == x else ""

    html_page = f"""
<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <title>RSVP Dashboard</title>
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <style>
    body{{font-family:system-ui,-apple-system,Segoe UI,Roboto,Arial,sans-serif;margin:0;background:#faf7f9;color:#333}}
    header{{position:sticky;top:0;background:#fff;border-bottom:1px solid #f1c1d7;padding:12px 16px;display:flex;gap:12px;align-items:center;flex-wrap:wrap}}
    h1{{font-size:20px;margin:0 12px 0 0;color:#b41c52}}
    .btn{{background:#ff2f73;color:#fff;border:none;border-radius:10px;padding:10px 14px;font-weight:700;text-decoration:none}}
    .btn:disabled{{opacity:.5}}
    .filters{{display:flex;gap:8px;align-items:center;flex-wrap:wrap}}
    .filters input,.filters select{{padding:8px;border:1px solid #f1c1d7;border-radius:8px}}
    main{{padding:16px;max-width:1100px;margin:0 auto}}
    table{{width:100%;border-collapse:collapse;background:#fff;border-radius:14px;overflow:hidden;box-shadow:0 8px 26px rgba(255,47,115,.10)}}
    thead th{{text-align:left;background:#fff1f5;border-bottom:1px solid #f1c1d7;padding:12px}}
    tbody td{{padding:10px;border-bottom:1px solid #f8e0ea;vertical-align:top}}
    .meta{{margin:10px 0;opacity:.8}}
    .pager{{display:flex;gap:8px;align-items:center;margin-top:12px}}
    .pill{{padding:6px 10px;border:1px solid #f1c1d7;border-radius:999px;background:#fff}}
    .right{{margin-left:auto}}
    @media (max-width:720px){{ thead{{display:none}} tbody td{{display:block}} tbody tr{{display:block;margin:10px 0;border:1px solid #f1c1d7;border-radius:12px}} tbody td::before{{content:attr(data-th) " ";font-weight:700;display:block;opacity:.7}} }}
  </style>
</head>
<body>
<header>
  <h1>RSVP Dashboard</h1>
  <a class="btn" href="/rsvp/export">⬇️ Baixar CSV</a>
  <form class="filters" method="get" action="{base}">
    <input type="text" name="q" placeholder="Buscar nome, email, mensagem" value="{esc(q) if q else ''}" />
    <select name="attend">
      <option value="">Presença (todos)</option>
      <option value="yes" {"selected" if attend=="yes" else ""}>Sim</option>
      <option value="no"  {"selected" if attend=="no" else ""}>Não</option>
    </select>
    <select name="order">
      <option value="created_at_desc" {sel("created_at_desc")}>Mais recentes</option>
      <option value="created_at_asc"  {sel("created_at_asc")}>Mais antigos</option>
      <option value="name_asc"        {sel("name_asc")}>Nome A→Z</option>
      <option value="name_desc"       {sel("name_desc")}>Nome Z→A</option>
    </select>
    <select name="size">
      <option { "selected" if size==25 else ""}>25</option>
      <option { "selected" if size==50 else ""}>50</option>
      <option { "selected" if size==100 else ""}>100</option>
    </select>
    <button class="btn" type="submit">Filtrar</button>
    <a class="pill right">Total: {total}</a>
  </form>
</header>
<main>
  <div class="meta">Página {page} • Mostrando até {size} por página</div>
  <table>
    <thead>
      <tr><th>ID</th><th>Data</th><th>Nome</th><th>Email</th><th>Presença</th><th>Mensagem</th></tr>
    </thead>
    <tbody>
      {"".join(
        f'<tr>'
        f'<td data-th="ID">{esc(r[0])}</td>'
        f'<td data-th="Data">{esc(r[1])}</td>'
        f'<td data-th="Nome">{esc(r[2])}</td>'
        f'<td data-th="Email"><a href="mailto:{esc(r[3])}">{esc(r[3])}</a></td>'
        f'<td data-th="Presença">{"✅" if r[4]=="yes" else "❌"}</td>'
        f'<td data-th="Mensagem">{esc(r[5])}</td>'
        f'</tr>'
        for r in rows
      )}
    </tbody>
  </table>
  <div class="pager">
    {"<a class='btn' href='"+prev_link+"'>◀️ Anterior</a>" if prev_link else "<button class='btn' disabled>◀️ Anterior</button>"}
    {"<a class='btn' href='"+next_link+"'>Próxima ▶️</a>" if next_link else "<button class='btn' disabled>Próxima ▶️</button>"}
  </div>
</main>
</body>
</html>
"""
    return HTMLResponse(content=html_page)

