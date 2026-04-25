import os
import json
import httpx
from flask import Flask, request, jsonify, render_template
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")
ANTHROPIC_KEY = os.environ.get("ANTHROPIC_KEY", "")

HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=representation",
}

def sb_get(table, params=None):
    url = f"{SUPABASE_URL}/rest/v1/{table}"
    r = httpx.get(url, headers=HEADERS, params=params, timeout=15)
    r.raise_for_status()
    return r.json()

def sb_post(table, data):
    url = f"{SUPABASE_URL}/rest/v1/{table}"
    r = httpx.post(url, headers=HEADERS, json=data, timeout=15)
    r.raise_for_status()
    return r.json()

def sb_patch(table, record_id, data):
    url = f"{SUPABASE_URL}/rest/v1/{table}"
    r = httpx.patch(url, headers=HEADERS, json=data,
                    params={"id": f"eq.{record_id}"}, timeout=15)
    r.raise_for_status()
    return r.json()

def sb_delete(table, record_id):
    url = f"{SUPABASE_URL}/rest/v1/{table}"
    r = httpx.delete(url, headers=HEADERS,
                     params={"id": f"eq.{record_id}"}, timeout=15)
    r.raise_for_status()

def file_exists(filename):
    try:
        result = sb_get("candidatos", {
            "filename": f"eq.{filename}",
            "select": "id",
            "limit": "1"
        })
        return len(result) > 0
    except:
        return False

def extract_with_ai(base64_data, filename):
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    is_image = ext in ("jpg", "jpeg", "png")
    is_pdf = ext == "pdf"
    if not is_image and not is_pdf:
        return {}
    if is_image:
        media_type = "image/png" if ext == "png" else "image/jpeg"
        content = [
            {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": base64_data}},
            {"type": "text", "text": "Curriculo. Retorne SOMENTE JSON sem texto adicional: {\"nome\":\"\",\"email\":\"\",\"telefone\":\"\",\"cargo\":\"\",\"resumo\":\"\",\"sexo\":\"M ou F ou desconhecido\",\"cidade\":\"\",\"idade\":0}. idade deve ser numero inteiro ou 0 se desconhecido."}
        ]
    else:
        content = [
            {"type": "document", "source": {"type": "base64", "media_type": "application/pdf", "data": base64_data}},
            {"type": "text", "text": "Curriculo. Retorne SOMENTE JSON sem texto adicional: {\"nome\":\"\",\"email\":\"\",\"telefone\":\"\",\"cargo\":\"\",\"resumo\":\"\",\"sexo\":\"M ou F ou desconhecido\",\"cidade\":\"\",\"idade\":0}. idade deve ser numero inteiro ou 0 se desconhecido."}
        ]
    r = httpx.post(
        "https://api.anthropic.com/v1/messages",
        headers={"x-api-key": ANTHROPIC_KEY, "anthropic-version": "2023-06-01", "content-type": "application/json"},
        json={"model": "claude-haiku-4-5-20251001", "max_tokens": 500, "messages": [{"role": "user", "content": content}]},
        timeout=60,
    )
    r.raise_for_status()
    text = r.json()["content"][0]["text"]
    text = text.replace("```json", "").replace("```", "").strip()
    return json.loads(text)

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/candidatos", methods=["GET"])
def get_candidatos():
    try:
        data = sb_get("candidatos", {"order": "created_at.desc", "limit": "1000"})
        return jsonify(data)
    except Exception as e:
        print(f"GET error: {e}")
        return jsonify([]), 200

@app.route("/api/candidatos", methods=["POST"])
def add_candidato():
    try:
        payload = request.json.copy()
        base64_data = payload.pop("base64", None)
        filename = payload.get("filename", "arquivo")

        if file_exists(filename):
            print(f"Duplicate skipped: {filename}")
            return jsonify({"skipped": True, "filename": filename}), 200

        info = {}
        if base64_data:
            try:
                info = extract_with_ai(base64_data, filename)
            except Exception as e:
                print(f"AI error for {filename}: {e}")

        idade = info.get("idade")
        if not isinstance(idade, int) or idade <= 0:
            idade = None

        payload.update({
            "nome":     info.get("nome") or filename.rsplit(".", 1)[0],
            "email":    info.get("email") or "-",
            "telefone": info.get("telefone") or "-",
            "cargo":    info.get("cargo") or "-",
            "resumo":   info.get("resumo") or "",
            "sexo":     info.get("sexo") or "desconhecido",
            "cidade":   info.get("cidade") or "-",
            "idade":    idade,
        })

        result = sb_post("candidatos", payload)
        return jsonify(result), 201

    except Exception as e:
        print(f"POST error: {e}")
        return jsonify({"error": str(e)}), 500

@app.route("/api/candidatos/<record_id>", methods=["PATCH"])
def update_candidato(record_id):
    try:
        data = sb_patch("candidatos", record_id, request.json)
        return jsonify(data)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/candidatos/<record_id>", methods=["DELETE"])
def delete_candidato(record_id):
    try:
        sb_delete("candidatos", record_id)
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/stats")
def get_stats():
    try:
        data = sb_get("candidatos", {"select": "etapa,sexo,cidade,idade,departamento", "limit": "2000"})
        total = len(data)
        entrevistados = len([c for c in data if c.get("etapa") in ("chamado","entrevistado","aprovado")])
        aprovados = len([c for c in data if c.get("etapa") == "aprovado"])
        
        # Sexo
        masc = len([c for c in data if str(c.get("sexo","")).upper().startswith("M")])
        fem = len([c for c in data if str(c.get("sexo","")).upper().startswith("F")])
        outro = total - masc - fem

        # Cidades
        cidades = {}
        for c in data:
            cidade = c.get("cidade") or "-"
            if cidade and cidade != "-":
                cidades[cidade] = cidades.get(cidade, 0) + 1
        cidades_sorted = sorted(cidades.items(), key=lambda x: x[1], reverse=True)[:10]

        # Idades
        idades = [c.get("idade") for c in data if c.get("idade") and isinstance(c.get("idade"), int) and c.get("idade") > 0]
        media_idade = round(sum(idades)/len(idades), 1) if idades else 0
        
        faixas = {"18-25": 0, "26-35": 0, "36-45": 0, "46+": 0}
        for i in idades:
            if i <= 25: faixas["18-25"] += 1
            elif i <= 35: faixas["26-35"] += 1
            elif i <= 45: faixas["36-45"] += 1
            else: faixas["46+"] += 1

        return jsonify({
            "total": total,
            "entrevistados": entrevistados,
            "aprovados": aprovados,
            "taxa_entrevista": round(entrevistados/total*100, 1) if total else 0,
            "taxa_aprovacao": round(aprovados/total*100, 1) if total else 0,
            "sexo": {"M": masc, "F": fem, "outro": outro},
            "cidades": cidades_sorted,
            "media_idade": media_idade,
            "faixas_idade": faixas,
        })
    except Exception as e:
        print(f"STATS error: {e}")
        return jsonify({}), 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
