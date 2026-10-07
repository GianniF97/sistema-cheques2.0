import os
from decimal import Decimal
from pathlib import Path
from flask import Flask, render_template, request, redirect, url_for, session, flash
import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv

# Fuerza la carga del archivo .env ubicado en la raíz del proyecto
BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(dotenv_path=BASE_DIR / ".env", override=True)

app = Flask(__name__, template_folder="../templates", static_folder="../static")
app.secret_key = os.environ.get("SECRET_KEY", "clave-secreta-temporal-2026")

def get_db():
    db_url = os.environ.get("DATABASE_URL", "")
    if not db_url:
        raise ValueError("DATABASE_URL no está configurada en el .env")
    return psycopg2.connect(db_url, cursor_factory=RealDictCursor)



def formato_ars(valor):
    try:
        val = float(valor or 0.0)
        return f"$ {val:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except (ValueError, TypeError):
        return "$ 0,00"

app.jinja_env.filters['ars'] = formato_ars

# --- CONTROL DE ACCESO ---
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        usuario = request.form.get("usuario", "").strip().lower()
        clave = request.form.get("clave", "").strip()

        admin_user = os.environ.get("ADMIN_USER", "").strip().lower()
        admin_pass = os.environ.get("ADMIN_PASS", "").strip()

        if usuario == admin_user and clave == admin_pass:
            session["logueado"] = True
            return redirect(url_for("cartera"))
        return render_template("login.html", error="Credenciales incorrectas")

    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

# --- VISTA: CARTERA DE CHEQUES ---
@app.route("/")
def cartera():
    if not session.get("logueado"):
        return redirect(url_for("login"))
    
    conn = get_db()
    cur = conn.cursor()
    
    cur.execute("""
        SELECT id, numero, tipo, emisor, banco, monto, 
               fecha_emision, fecha_pago, estado, entregado_a, fecha_entrega 
        FROM cheques 
        ORDER BY fecha_pago ASC;
    """)
    cheques = cur.fetchall()
    
    total_monto = sum(Decimal(c["monto"] or 0) for c in cheques)
    pendientes = [c for c in cheques if str(c.get("estado", "")).lower() == "pendiente"]
    total_pendiente = sum(Decimal(c["monto"] or 0) for c in pendientes)
    cant_pendientes = len(pendientes)
    
    cur.close()
    conn.close()
    
    return render_template(
        "cartera.html",
        cheques=cheques,
        total_monto=total_monto,
        total_pendiente=total_pendiente,
        cant_pendientes=cant_pendientes
    )

# --- VISTA: REGISTRAR CHEQUE ---
@app.route("/registrar", methods=["GET", "POST"])
def registrar():
    if not session.get("logueado"):
        return redirect(url_for("login"))
    
    if request.method == "POST":
        numero = request.form.get("numero", "").strip()
        emisor = request.form.get("emisor", "").strip()
        banco = request.form.get("banco", "").strip()
        tipo = request.form.get("tipo", "Físico")
        monto = request.form.get("monto", "0.0")
        f_emision = request.form.get("f_emision")
        f_pago = request.form.get("f_pago")
        
        try:
            conn = get_db()
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO cheques (numero, tipo, emisor, banco, monto, fecha_emision, fecha_pago, estado)
                VALUES (%s, %s, %s, %s, %s, %s, %s, 'pendiente');
            """, (numero, tipo, emisor, banco, float(monto), f_emision, f_pago))
            conn.commit()
            cur.close()
            conn.close()
            flash("Cheque registrado con éxito", "success")
            return redirect(url_for("cartera"))
        except Exception as e:
            flash(f"Error al guardar: {str(e)}", "danger")
            
    return render_template("registrar.html")

# --- VISTA: OPERACIONES (CAMBIAR ESTADO) ---
@app.route("/operaciones", methods=["POST"])
def cambiar_estado():
    if not session.get("logueado"):
        return redirect(url_for("login"))
    
    numero = request.form.get("numero_cheque", "").strip()
    accion = request.form.get("accion")
    destinatario = request.form.get("destinatario", "").strip()
    
    conn = get_db()
    cur = conn.cursor()
    
    if accion == "Depositar en Banco":
        cur.execute("""
            UPDATE cheques 
            SET estado = 'depositado', entregado_a = 'Banco', fecha_entrega = CURRENT_DATE 
            WHERE numero = %s;
        """, (numero,))
    elif accion == "Entregar a Tercero":
        cur.execute("""
            UPDATE cheques 
            SET estado = 'entregado', entregado_a = %s, fecha_entrega = CURRENT_DATE 
            WHERE numero = %s;
        """, (destinatario, numero))
        
    conn.commit()
    cur.close()
    conn.close()
    flash("Estado actualizado correctamente", "success")
    return redirect(url_for("cartera"))

if __name__ == "__main__":
    app.run(debug=True, port=5000)