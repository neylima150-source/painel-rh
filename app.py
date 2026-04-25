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

# ── Detecção de sexo por nome ──────────────────────────────────────────────

NOMES_M = set("""joao jose carlos antonio francisco paulo pedro lucas gabriel
rafael daniel marcos luis felipe andre rodrigo fernando fabio leonardo
mateus vitor guilherme igor thiago leandro marcelo samuel alan alex
anderson bruno cesar claudio cristiano davi diego edson eduardo elvis
emerson erick evandro ezequiel fabricio gilberto gustavo henrique hugo
ivan jorge julio junior luan mauro maxwell messias michel murilo natanael
neto newton nilson omar oscar paulo pedro rafael ramiro renan renato
ricardo roberto robson rodrigo rogerio ruan ruben saulo sergio silas
silvio tiago vinicius wagner walter wellington wellington wendell willian
william alex alexandre alexsander alfredo alisson anderson andre
antonio artur augusto benicio benjamin bernardo beto brayan brenno caio
caleb camilo cassio cauã claudio cleber cleiton cleto clovis cristobal
davi deyson diego dirceu donizete edimilson edilson ednaldo edson edvaldo
enzo eraldo erick ezequiel fabrício fellipe fernado francisco frederico
gabriel gean gedeon geovane gilson giovani giovanny giovanni glauber
gleison gleidson gledson gledione graciliano gregor gustavo henrique
heitor helton hiago humberto igor isaque ivan jackson jairo janderson
janeudo janio jefferson jeferson jhonas jhonatan joab joaquim joel
jonatan jonas jonathan jorge josias josiel juarez juliao julio kaio
kauã kelvin kesley kevin kleber kleberson kleyton levi leandro leonardo
leogildo leonardo levi lucas lucio luiz lukas lumack luiz luan macedonio
marcelo marcio mario matheus mauro maxwell maycon melquisedeque messias
michell milson misael moises murilo natan nathan nem neemias nicolas
nilton norberto odair odilon odilon odones oilson olavo olimpio omar
osiris osmar osvaldo otavio pablo pantaliao pascal pericles perseu
phelipe philipe priscilo rafael railson ramiro ramom ramsés raner raul
reginaldo reinaldo renan renato ribamar richard rivaldo roberto robson
rodrigo rogerio romario romulo ronaldo roney ronieri roque rorys ruben
rubens samuel saul saulo savio sergio silvano silverio silvio simiao
sinivaldo sirley sirlei stive tainã tainã talles tarcisio tasio tawan
thiago tiago tito tobias tomaz tulio vagner valdecir valdecir valdemiro
valdir valter vanderlei vinicius vitor walace walber waldimir waldix
walisson walmor wanderlei washington welinton welison welton wender
wenderson weslei wessley widson wilder wilington willians willians
william yago yuri zeus""".split())

NOMES_F = set("""maria ana paula fernanda patricia juliana sandra camila
beatriz carolina amanda larissa leticia mariana aline gabriela jessica
raquel luciana denise cristina claudia adriana helena vanessa isabela
natalia bianca simone tatiane elaine viviane kelly jaqueline luana
priscila micheli bruna renata andreia debora daiane fabiana michele
luciene rosana rosangela roseli roseli silvia silvana sueli suely
tais tamara tamiris tatiana thais thainá thainara thainá valentina
veridiana veronica vivian viviane walquiria wanderléa wanessa wanuza
welinete wendy wendeline wesline wilma yara yasmin zelia zenaide
abigail agatha agnes alessandra alicia aline alícia aliona aloisia
amelia ana anacleia anailda analice ananda anavia andréia angela anice
anielze anita anisia anjanuara anna annick anny antonia antonieta arlete
augustinha aurea aurelia aurora auxiliadora beatriz berenice betânia
bianca brenda bruna brunela camilla carla carlota carmem cassandra cátia
célia celida celina christiane cibele cida cidinha cinara cintia claire
claudete claudia claúdia cleonice cleria cleudes cleuza clia conceição
consuelo cora cristiane cristina cyntia dagmar daiane dalva damaris
damiana dania daniela danielle dara dayane débora deise dejanara delci
delmira diana dinalva diva dolores domingas doralice dulce dulcineia
ecléia edinha edite edmara edna edvanilda elaine eliana eliene elisa
elise elizabete elizangela elizete ellen elly eloisa elza emilia emiliana
enedina erika ester esther eugenia eunice evandra evangelina eveli evelyn
ezilda fabiana fabiola fatima fernanda filomena flavinha flavia franci
francisca francielly franciele francesca gabi genizia geovana geovanna
gerlane girlane gisele gislaine gloria graça graciela graziela grazielle
haidê helenice heloisa heloísa hortencia iara idalia ilca ilza iolanda
iracema iraci iraides irani irinéia iris irma isabel isadora isadora
isadora ivana ivanete ivanice ivete ivone jacinta jaqueline jasmine jéssica
joana jocelia joelma josefa josiane josimar jovita judith julia juliana
juliane julieta junara karina karla katia kátia keila kelly kely ketlin
laiane laísa lalesca laura lavinia layane leandro leanne lelia lena leonora
leticia lidia liège lilian liliane linda lindinalva liz loide lourdes luana
luanna lucia luciana luciene lucilene lucimara lucineia lucineide luise
lurdes luzia luzia luzimar madalena madeja maira manuela marcela marcia
margarida maria marialva mariangela marianne marilene marilia mariluce
mariluci mariluz marina marise marisete maritê mariza marlene marli marluci
marluse marly marta marusa mary massilon mayara mayrla melina melissa
meire meiriane micheli michelline mikaela milena mileidy miriam mirian
missangela mônica morena muriele nádia natalia natalina nathalia nathaly
nayara neide neila neuza nicoly nicole nina noemi nora norma odete olga
olinda olusegun ondina paloma pamela pandora paola patricia paty paula
paulina pauline perla petronilha pietra porfiria priscila priscilla
queila quezia quilma quimia rachel rafaela raimunda raissa ramona ranielle
raquel rebeca reinalda renata renate rita roana roberta rosi rosana rosane
rosangela rosaria rose roseli rosemeire roseni rosenir rosiane rosimara
rosimar rosimeira rosinei rosinéia rossana ruth sabrina samara samira
sandra sania sara sarah selma silvana silvanete silvaneide silvia simone
sionara sirlei sirley solange sonia sueli suely susana susane suseli
tainá tainara talita tamara tana tania tatiana terezinha thais thalita
thalia thamara thifani thifany uiara valdete valeria valéria valnice
valquíria vanessa vania vânia vanilda vera veronica vicencia vilma
virginia viviane waldineia waleska walesca walkyria wanessa wania wardinha
yasmin yolanda yolanda zaira zenilda zélia zilka zilma zilmira zita""".split())

def inferir_sexo_por_nome(nome):
    if not nome:
        return "desconhecido"
    primeiro = nome.strip().split()[0].lower()
    # Remove acentos simples para comparação
    import unicodedata
    primeiro_sem_acento = ''.join(
        c for c in unicodedata.normalize('NFD', primeiro)
        if unicodedata.category(c) != 'Mn'
    )
    if primeiro_sem_acento in NOMES_M or primeiro in NOMES_M:
        return "M"
    if primeiro_sem_acento in NOMES_F or primeiro in NOMES_F:
        return "F"
    return "desconhecido"


@app.route("/api/atualizar-sexo", methods=["POST"])
def atualizar_sexo():
    """Atualiza sexo de todos os candidatos sem sexo definido usando o nome."""
    try:
        candidatos = sb_get("candidatos", {
            "select": "id,nome,sexo",
            "limit": "2000"
        })
        atualizados = 0
        for c in candidatos:
            if c.get("sexo") in (None, "", "desconhecido", "-"):
                sexo = inferir_sexo_por_nome(c.get("nome",""))
                if sexo != "desconhecido":
                    sb_patch("candidatos", c["id"], {"sexo": sexo})
                    atualizados += 1
        return jsonify({"ok": True, "atualizados": atualizados})
    except Exception as e:
        print(f"ATUALIZAR-SEXO error: {e}")
        return jsonify({"error": str(e)}), 500
