import os
import json
import re
import httpx
import unicodedata
from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
from datetime import datetime

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

def get_existing(filename):
    try:
        result = sb_get("candidatos", {
            "filename": f"eq.{filename}",
            "select": "id,sexo,cidade,idade",
            "limit": "1"
        })
        return result[0] if result else None
    except:
        return None

def calcular_meses(entrada, saida):
    """Calcula meses entre duas datas no formato MM/YYYY ou YYYY"""
    try:
        def parse_data(d):
            d = str(d).strip()
            if re.match(r'^\d{4}$', d):
                return datetime(int(d), 1, 1)
            if re.match(r'^\d{2}/\d{4}$', d):
                m, y = d.split('/')
                return datetime(int(y), int(m), 1)
            if re.match(r'^\d{4}/\d{2}$', d):
                y, m = d.split('/')
                return datetime(int(y), int(m), 1)
            return None
        
        d1 = parse_data(entrada)
        d2 = parse_data(saida) if saida and str(saida).lower() not in ('atual','presente','current','') else datetime.now()
        if d1 and d2:
            return max(0, (d2.year - d1.year) * 12 + (d2.month - d1.month))
    except:
        pass
    return None

def extract_with_ai(base64_data, filename):
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    is_image = ext in ("jpg", "jpeg", "png")
    is_pdf = ext == "pdf"
    if not is_image and not is_pdf:
        return {}
    
    prompt = """Analise este curriculo e retorne SOMENTE um JSON com esta estrutura exata:
{
  "nome": "",
  "email": "",
  "telefone": "",
  "cargo": "",
  "resumo": "",
  "sexo": "M ou F ou desconhecido",
  "cidade": "",
  "idade": 0,
  "historico": [
    {
      "empresa": "",
      "cargo": "",
      "setor": "industria ou comercio ou servicos ou construcao ou saude ou educacao ou tecnologia ou agronegocio ou outro",
      "data_entrada": "MM/YYYY",
      "data_saida": "MM/YYYY ou atual",
      "emprego_atual": false
    }
  ]
}
Retorne SOMENTE o JSON, sem texto adicional."""

    if is_image:
        media_type = "image/png" if ext == "png" else "image/jpeg"
        content = [
            {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": base64_data}},
            {"type": "text", "text": prompt}
        ]
    else:
        content = [
            {"type": "document", "source": {"type": "base64", "media_type": "application/pdf", "data": base64_data}},
            {"type": "text", "text": prompt}
        ]
    
    r = httpx.post(
        "https://api.anthropic.com/v1/messages",
        headers={"x-api-key": ANTHROPIC_KEY, "anthropic-version": "2023-06-01", "content-type": "application/json"},
        json={"model": "claude-haiku-4-5-20251001", "max_tokens": 1500, "messages": [{"role": "user", "content": content}]},
        timeout=90,
    )
    r.raise_for_status()
    text = r.json()["content"][0]["text"]
    text = text.replace("```json", "").replace("```", "").strip()
    return json.loads(text)

NOMES_M = set("joao jose carlos antonio francisco paulo pedro lucas gabriel rafael daniel marcos luis felipe andre rodrigo fernando fabio leonardo mateus vitor guilherme igor thiago leandro marcelo samuel alan alex anderson bruno cesar diego eduardo gustavo henrique hugo ivan jorge julio junior luan mauro michel murilo renan renato ricardo roberto robson rogerio ruan sergio tiago vinicius wagner walter wellington william willian caio davi enzo heitor kaio kelvin kevin matheus nathan nicolas otavio raul ryan theo yuri adriano ailton alisson amauri arnaldo cezar cleber cleyton cristiano denilson edson emerson erick evandro ezequiel fabricio gilberto gilson gleison gledson jackson jairo jefferson jonatan jonas jonathan josias juarez kleber levi lucio luiz maycon messias moises natan nilton osvaldo pablo ramiro reginaldo reinaldo rivaldo romario romulo ronaldo rubens saulo silvio vanderlei wanderlei washington welinton wenderson yago elias eder edmar edinaldo edivaldo edmilson geovane giovani giovanni glauber graciliano hiago humberto isaque janderson jeferson jhonatan joaquim joel jonatas josiel macedonio marcio mario maxwell michell misael norberto odair olavo osmar pantaliao pericles railson richard rogerio roney ronieri roque silverio simiao sinivaldo stive tarcisio tobias tomaz tulio vagner valdecir valdemiro valdir valter walmor walace walber waldimir walisson widson wilder zeus cleverson cleilton afonso agostinho amilton artur augusto benedito bento bernardo brayan brenno caleb camilo cassio claudio cleiton deyson donizete ednaldo edvaldo eraldo everton ezequias frederico gean gedeon gleidson gledione gregor helton iuri jubileu kaique lauro lazaro leonidas luciano lukas mauricio maicon maximiliano neto newton nilson omar oscar percival perseu phelipe philipe priscilo ramom rones ruben salomao silvano sirlei talles tawan ubiratan ulisses valdomiro vasco venceslau wander wanel weverton wilton xisto zaqueu zenobio adrian cauã caua clayton danilo douglas emanoel emanuel emmanuel gesiel ian joao john jose leo licinei sandro thom gesiel".split())

NOMES_F = set("maria ana paula fernanda patricia juliana sandra camila beatriz carolina amanda larissa leticia mariana aline gabriela jessica raquel luciana denise cristina claudia adriana helena vanessa isabela natalia bianca simone tatiane elaine viviane kelly jaqueline luana priscila micheli bruna renata andreia debora daiane fabiana michele luciene rosana rosangela roseli silvia silvana sueli tais tamara tamiris tatiana thais valentina veronica yasmin abigail agatha agnes alessandra alicia amelia angela anita anna antonia arlete aurora beatriz berenice betania brenda brunela camilla carla carlota carmem cassandra catia celia celida celina christiane cibele cida cinara cintia clarice claudete claudia cleonice cleudes cleuza conceicao consuelo cristiane cyntia dagmar dalva damaris daniela danielle dayane debora deise delci diana dinalva diva dolores domingas doralice dulce eliana eliene elisa elizabete elizangela elizete ellen eloisa elza emilia erika ester esther eugenia eunice evandra evangelina eveli evelyn fabiana fabiola fatima flavia francisca francielly franciele gabi genizia geovana geovanna gisele gislaine gloria graca graciela graziela grazielle heloisa iara ilca ilza iolanda iracema iris irma isabel isadora ivana ivanete ivanice ivete ivone jacinta jasmine joana jocelia joelma josefa josiane jovita judith julia juliane julieta junara karina karla katia keila laiane laisa lalesca laura lavinia layane leanne lelia lena leonora lidia lilian liliane linda lindinalva liz loide lourdes lucia luciane lucilene lucimara lucineia luise lurdes luzia luzimar madalena maira manuela marcela marcia margarida mariangela marianne marilene marilia marina marise maritê mariza marlene marli marly marta mary mayara melina melissa meire micheli mikaela milena miriam mirian monica nadia natalina nathalia nathaly nayara neide neila neuza nicoly nicole nina noemi norma odete olga olinda paloma pamela paola paulina pauline perla pietra priscila priscilla queila quezia rachel rafaela raimunda raissa ramona ranielle rebeca reinalda rita roberta rosi rosane rosaria rose rosemeire roseni rosenir rosiane rosimara rosimar rosimeira rosinei rossana ruth sabrina samara samira selma silvane silvaneide sionara sirlei solange sonia susana susane suseli talita tania tatiana terezinha thalita thalia thamara thifani uiara valdete valeria valnice valquiria vania vanilda vera vicencia vilma virginia waldineia waleska walesca walkyria wanessa wania wardinha yolanda zaira zenilda zelia zilka zilma zilmira zita andressa angelica aparecida cicera cidinha cleide cleidiane cleonice creuza dalva darcilene edineia edineide edvania elcione eliene elienai eliete eliria elizabete emiliana enedina ezilda flavinha francielly geralda gislene gleiciane gleiciele iraides irani ivonete janaina janete jaqueline jilsimara joseane josiane keite laiane leidiane leidimar leila lindalva lindaura lucineia lucineide luisa marilaci marilena marineia marizete marluce marluse meirilene meiriane mirian nailza natalina neusa nilza onelia paulinha perpetua rafaelle raimunda rosemeire rosenei rosineide rosinalda rosineide rubia ruthiely samanta scheilla selia silvanete silvaneide simara sirlene taina tainara tainã thamires thifany valdirene valéria vanderlea wanderlea wanessa wesline wilma zenaide alanys alice andrea angelica anne arelita dara elayne etielly fabiola gabriele gabrielle gabrielly halicia helen indianara jessica joice kerolayne maysa meryellen nathali raphaella sara thayna".split())

def inferir_sexo_por_nome(nome):
    if not nome:
        return "desconhecido"
    primeiro = nome.strip().split()[0].lower()
    primeiro_sem_acento = ''.join(
        c for c in unicodedata.normalize('NFD', primeiro)
        if unicodedata.category(c) != 'Mn'
    )
    if primeiro_sem_acento in NOMES_M or primeiro in NOMES_M:
        return "M"
    if primeiro_sem_acento in NOMES_F or primeiro in NOMES_F:
        return "F"
    return "desconhecido"

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

        existing = get_existing(filename)

        info = {}
        if base64_data:
            try:
                info = extract_with_ai(base64_data, filename)
            except Exception as e:
                print(f"AI error for {filename}: {e}")

        idade = info.get("idade")
        if not isinstance(idade, int) or idade <= 0:
            idade = None

        sexo = info.get("sexo") or "desconhecido"
        if sexo == "desconhecido":
            sexo = inferir_sexo_por_nome(info.get("nome") or filename)

        cidade = info.get("cidade") or "-"
        historico = info.get("historico") or []

        if existing:
            update_data = {}
            if not existing.get("sexo") or existing.get("sexo") in ("desconhecido", "-", ""):
                update_data["sexo"] = sexo
            if not existing.get("cidade") or existing.get("cidade") in ("-", ""):
                update_data["cidade"] = cidade
            if not existing.get("idade") and idade:
                update_data["idade"] = idade
            if update_data:
                sb_patch("candidatos", existing["id"], update_data)

            # Salva historico se ainda nao tem
            hist_existente = sb_get("historico_empregos", {"candidato_id": f"eq.{existing['id']}", "select": "id", "limit": "1"})
            if not hist_existente and historico:
                for h in historico:
                    meses = calcular_meses(h.get("data_entrada"), h.get("data_saida"))
                    sb_post("historico_empregos", {
                        "candidato_id": existing["id"],
                        "empresa": h.get("empresa") or "",
                        "cargo": h.get("cargo") or "",
                        "setor": h.get("setor") or "outro",
                        "data_entrada": h.get("data_entrada") or "",
                        "data_saida": h.get("data_saida") or "",
                        "meses_permanencia": meses,
                        "emprego_atual": h.get("emprego_atual") or False,
                    })
            return jsonify({"updated": True, "filename": filename}), 200

        payload.update({
            "nome":     info.get("nome") or filename.rsplit(".", 1)[0],
            "email":    info.get("email") or "-",
            "telefone": info.get("telefone") or "-",
            "cargo":    info.get("cargo") or "-",
            "resumo":   info.get("resumo") or "",
            "sexo":     sexo,
            "cidade":   cidade,
            "idade":    idade,
        })

        result = sb_post("candidatos", payload)
        cand_id = result[0]["id"] if isinstance(result, list) else result.get("id")

        if cand_id and historico:
            for h in historico:
                meses = calcular_meses(h.get("data_entrada"), h.get("data_saida"))
                try:
                    sb_post("historico_empregos", {
                        "candidato_id": cand_id,
                        "empresa": h.get("empresa") or "",
                        "cargo": h.get("cargo") or "",
                        "setor": h.get("setor") or "outro",
                        "data_entrada": h.get("data_entrada") or "",
                        "data_saida": h.get("data_saida") or "",
                        "meses_permanencia": meses,
                        "emprego_atual": h.get("emprego_atual") or False,
                    })
                except Exception as e:
                    print(f"Historico error: {e}")

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

        masc = len([c for c in data if str(c.get("sexo","")).upper().startswith("M")])
        fem = len([c for c in data if str(c.get("sexo","")).upper().startswith("F")])
        outro = total - masc - fem

        cidades = {}
        for c in data:
            cidade = c.get("cidade") or "-"
            if cidade and cidade != "-":
                cidades[cidade] = cidades.get(cidade, 0) + 1
        cidades_sorted = sorted(cidades.items(), key=lambda x: x[1], reverse=True)[:3]

        idades = [c.get("idade") for c in data if c.get("idade") and isinstance(c.get("idade"), int) and c.get("idade") > 0]
        media_idade = round(sum(idades)/len(idades), 1) if idades else 0

        faixas = {"18-25": 0, "26-35": 0, "36-45": 0, "46+": 0}
        for i in idades:
            if i <= 25: faixas["18-25"] += 1
            elif i <= 35: faixas["26-35"] += 1
            elif i <= 45: faixas["36-45"] += 1
            else: faixas["46+"] += 1

        # Historico de empregos
        hist = sb_get("historico_empregos", {"select": "setor,meses_permanencia", "limit": "5000"})
        setores = {}
        for h in hist:
            if h.get("meses_permanencia") and h.get("setor"):
                s = h["setor"]
                if s not in setores:
                    setores[s] = []
                setores[s].append(h["meses_permanencia"])

        media_por_setor = {}
        for s, meses_list in setores.items():
            if meses_list:
                media_por_setor[s] = round(sum(meses_list)/len(meses_list), 1)

        media_geral = 0
        if hist:
            todos_meses = [h["meses_permanencia"] for h in hist if h.get("meses_permanencia")]
            if todos_meses:
                media_geral = round(sum(todos_meses)/len(todos_meses), 1)

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
            "media_permanencia_geral": media_geral,
            "media_por_setor": media_por_setor,
            "total_historicos": len(hist),
        })
    except Exception as e:
        print(f"STATS error: {e}")
        return jsonify({}), 500

@app.route("/api/atualizar-sexo", methods=["POST"])
def atualizar_sexo():
    try:
        candidatos = sb_get("candidatos", {"select": "id,nome,sexo", "limit": "2000"})
        atualizados = 0
        for c in candidatos:
            if c.get("sexo") in (None, "", "desconhecido", "-"):
                sexo = inferir_sexo_por_nome(c.get("nome",""))
                if sexo != "desconhecido":
                    sb_patch("candidatos", c["id"], {"sexo": sexo})
                    atualizados += 1
        return jsonify({"ok": True, "atualizados": atualizados})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
