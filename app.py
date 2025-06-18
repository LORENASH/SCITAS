from flask import Flask, render_template, request, redirect, send_file, url_for, session
import mysql.connector
from datetime import datetime, timedelta
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
import io
from datetime import datetime, timedelta
import calendar
import sys
from datetime import date
import os
import json
#from werkzeug.security import generate_password_hash, check_password_hash

#import pymysql
#render
from dotenv import load_dotenv

app = Flask(__name__)
#disponibilidad_medicos
disponibilidad_medicos = {}

nombres_con_titulo = {
    "Dra. Laymito": "Dra. Laymito",
    "Dr. Correa": "Dr. Correa",
    "Dra. Julia": "Dra. Julia",
    "Dr. Isla": "Dr. Isla",
    "Dr. Figueroa": "Dr. Figueroa"
}

#anterior
# def get_db_connection():
    # import mysql.connector
    # return mysql.connector.connect(
        # host="localhost",
        # user="root",
        # password="",
        # database="modulo"
    # )

#root
# def conectar_bd(): 
    # return mysql.connector.connect(
        # host="localhost",
        # user="root",
        # password="",  
        # database="modulo"
 #  )
#carga las variables de entorno de env Render
load_dotenv()

    
#carga la coenxion con las variables de entorno de env   
def conectar_bd():
    return mysql.connector.connect(
        host=os.getenv("DB_HOST"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASS"),
        database=os.getenv("DB_NAME")
    )

conexion = conectar_bd()
cursor = conexion.cursor()

def obtener_disponibilidad_actual():
    conexion = conectar_bd()
    cursor = conexion.cursor()
    hoy = datetime.now()
    mes, anio = hoy.month, hoy.year
    cursor.execute("SELECT medico, dia FROM disponibilidad WHERE mes = %s AND anio = %s", (mes, anio))
    datos = cursor.fetchall()
    cursor.close()
    conexion.close()

    disponibilidad_medicos = {}
    for medico, dia in datos:
        # if dia == 6:
            # continue  # omitimos domingos
        disponibilidad_medicos.setdefault(medico, []).append(dia)
    return disponibilidad_medicos


@app.route('/disponibilidad', methods=['GET', 'POST'])
def disponibilidad():
    if request.method == 'POST':
        medico = request.form['medico']
        dias = request.form.getlist('dias')
        hoy = date.today()
        mes = hoy.month
        anio = hoy.year

        cursor = conexion.cursor()
        cursor.execute("DELETE FROM disponibilidad WHERE medico = %s AND mes = %s AND anio = %s", (medico, mes, anio))
        for dia in dias:
            cursor.execute("INSERT INTO disponibilidad (medico, dia, mes, anio) VALUES (%s, %s, %s, %s)",
                           (medico, int(dia), mes, anio))
        conexion.commit()
        return render_template('disponibilidad.html', mensaje='✅ Disponibilidad guardada correctamente.')

    return render_template('disponibilidad.html')



@app.route('/guardar', methods=['POST'])
def guardar():
    conn = conectar_bd()
    cursor = conn.cursor()

    nombre = request.form["nombre"]
    dni = request.form["dni"]
    fecha_str = request.form["fecha"]
    medico = request.form["medico"]
    
    hoy = datetime.now()
    mes = hoy.month
    anio = hoy.year

    disponibilidad_medicos = obtener_disponibilidad_actual()

    offset = request.form.get('offset', '').strip()
    if not offset:
        conn.close()
        return "Error: Debes elegir un plazo.", 400

    if offset == 'personalizado':
        custom = request.form.get('offset_custom', '').strip()
        if not custom:
            conn.close()
            return "Error: Ingresa un número de días personalizado (1–29).", 400
        if not custom.isdigit() or not (1 <= int(custom) <= 29):
            conn.close()
            return "Error: El número personalizado debe ser un entero entre 1 y 29.", 400
        delta_dias = int(custom)
    else:
        if not offset.isdigit():
            conn.close()
            return "Error: Plazo inválido.", 400
        delta_dias = int(offset)

    # Fecha tentativa inicial
    fecha = datetime.strptime(fecha_str, "%Y-%m-%d")
    proxima_fecha = fecha + timedelta(days=delta_dias)

    disponibilidad = list(map(int, disponibilidad_medicos.get(medico, [])))
    if not disponibilidad:
        conn.close()
        return "⚠️ No hay días disponibles para este médico.", 400

    # Buscar fecha válida con disponibilidad
    ajustada = False
    intentos = 0
    while True:
        if (proxima_fecha.weekday()+1) in disponibilidad:
            cursor.execute("""
                SELECT COUNT(*) FROM pacientes
                WHERE medico = %s AND proxima_fecha = %s
            """, (medico, proxima_fecha.strftime("%Y-%m-%d")))
            cantidad = cursor.fetchone()[0]

            if cantidad < 12:
                break  # Fecha válida encontrada

        proxima_fecha += timedelta(days=1)
        ajustada = True
        intentos += 1
        if intentos > 60:
            cursor.close()
            conn.close()
            return "⚠️ No se encontró una fecha disponible en los próximos 60 días.", 400
            
    cursor.execute("""
        INSERT INTO pacientes (nombre, dni, fecha, medico, proxima_fecha)
        VALUES (%s, %s, %s, %s, %s)
    """, (nombre, dni, fecha_str, medico, proxima_fecha.strftime("%Y-%m-%d")))
    conn.commit()

    cursor.close()
    conn.close()
    
    
#CAMBIO formato fecha aqui dmy
    nombre_mostrar = nombres_con_titulo.get(medico, medico)
    return render_template("confirmar_fecha.html", nombre=nombre, dni=dni,
                           #fecha=fecha_str,
                           fecha= datetime.strptime(fecha_str, "%Y-%m-%d").strftime("%d/%m/%Y"),                           
                           medico=medico,
                           nombre_mostrar=nombre_mostrar,
                           proxima_fecha=proxima_fecha.strftime("%d-%m-%Y"),
                           ajustada=ajustada)


from flask import send_file, request
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
import io

@app.route('/reporte', methods=['GET', 'POST'])
def reporte():
    try:
        # Obtener filtros
        medico = request.form.get('medico', '')
        proximafecha = request.form.get('proxima_fecha', '')
        mes_anio = request.form.get('mes_anio', '')

        conexion = conectar_bd()
        cursor = conexion.cursor()

        query = "SELECT nombre, dni, fecha, proxima_fecha, medico FROM pacientes WHERE 1=1"
        params = []

        if medico:
            query += " AND medico = %s"
            params.append(medico)
        if proximafecha:
            query += " AND proxima_fecha = %s"
            params.append(proximafecha)
        if mes_anio:
            anio, mes = mes_anio.split('-')
            query += " AND MONTH(proxima_fecha) = %s AND YEAR(proxima_fecha) = %s"
            params.extend([int(mes), int(anio)])

        cursor.execute(query, tuple(params))
        pacientes = cursor.fetchall()

        if not pacientes:
            return "No se encontraron pacientes con esos filtros."

        # Agrupar por médico
        pacientes_por_medico = {}
        for p in pacientes:
            nombre, dni, fecha, proxima, medico_actual = p
            pacientes_por_medico.setdefault(medico_actual, []).append((nombre, dni, fecha, proxima))

        # PDF
        buffer = io.BytesIO()
        c = canvas.Canvas(buffer, pagesize=letter)
        y = 750

        # Título dinámico
        c.setFont("Helvetica-Bold", 14)
        c.drawCentredString(300, y, "Reporte de Pacientes")
        y -= 30

        if mes_anio:
            c.setFont("Helvetica", 12)
            c.drawString(50, y, f"Mes/Año: {mes_anio}")
            y -= 20
        elif proximafecha:
            c.setFont("Helvetica", 12)
            c.drawString(50, y, f"Fecha específica: {proximafecha}")
            y -= 20

        # Coordenadas tabla
        x_nombre = 50
        x_dni = 200
        x_fecha = 280
        x_proxima = 360
       

        for medico_actual in sorted(pacientes_por_medico.keys()):
            c.setFont("Helvetica-Bold", 12)
            c.drawString(50, y, f"Médico: {medico_actual}")
            y -= 20

            # Cabecera de tabla
            c.setFont("Helvetica-Bold", 10)
            c.drawString(x_nombre, y, "Nombre")
            c.drawString(x_dni, y, "DNI")
            c.drawString(x_fecha, y, "Fecha")
            c.drawString(x_proxima, y, "Próxima")
            y -= 10
            c.line(50, y, 550, y)
            y -= 10

            c.setFont("Helvetica", 10)
            for nombre, dni, fecha, proxima in pacientes_por_medico[medico_actual]:
                fecha_str = fecha.strftime("%d/%m/%Y")
                proxima_str = proxima.strftime("%d/%m/%Y")

                c.drawString(x_nombre, y, nombre)
                c.drawString(x_dni, y, dni)
                c.drawString(x_fecha, y, fecha_str)
                c.drawString(x_proxima, y, proxima_str)
                
                y -= 20

                if y < 60:
                    c.showPage()
                    y = 750
                    c.setFont("Helvetica", 10)

            # Total por médico
            y -= 5
            c.setFont("Helvetica-Bold", 10)
            c.drawString(60, y, f"Total de pacientes de {medico_actual}: {len(pacientes_por_medico[medico_actual])}")
            y -= 30

        # Total general
        c.setFont("Helvetica-Bold", 11)
        c.drawString(50, y, f"Total de pacientes: {len(pacientes)}")

        c.save()
        buffer.seek(0)
        return send_file(buffer, as_attachment=True, download_name="reporte.pdf", mimetype='application/pdf')

    except Exception as e:
        return f"Error al generar el reporte: {str(e)}"



@app.route('/ver_disponibilidad')
def ver_disponibilidad():
    conexion = conectar_bd()
    cursor = conexion.cursor()
    hoy = datetime.now()
    año, mes = hoy.year, hoy.month

    # Leer disponibilidad desde base de datos (1 = lunes, ..., 6 = sábado)
    cursor.execute("SELECT medico, dia FROM disponibilidad WHERE mes=%s AND anio=%s", (mes, año))
    datos = cursor.fetchall()
    conexion.close()

    # Agrupar médicos por día (1 a 6)
    dispo_por_weekday = {}
    for medico, weekday in datos:
        dispo_por_weekday.setdefault(weekday, []).append(medico)

    # Generar semanas del mes actual
    cal = calendar.Calendar()
    semanas = []
    for semana in cal.monthdayscalendar(año, mes):
        semana_data = []
        for dia in semana:
            if dia == 0:
                semana_data.append({'dia': 0, 'medicos': []})  # Día vacío
            else:
                wd = datetime(año, mes, dia).weekday() + 1  # Ajustamos: 1 = lunes, ..., 7 = domingo
                if wd <= 6:  # Solo lunes a sábado
                    semana_data.append({
                        'dia': dia,
                        'medicos': dispo_por_weekday.get(wd, [])
                    })
                else:
                    semana_data.append({'dia': dia, 'medicos': []})  # Domingo vacío
        semanas.append(semana_data)

    return render_template(
        'calendar.html',
        semanas=semanas,
        mes=mes,
        anio=año
    )


@app.route('/multi_calendario')
def multi_calendario():
    conexion = conectar_bd()
    cursor = conexion.cursor()
    hoy = datetime.now()
    mes0, año0 = hoy.month, hoy.year

    # Filtro por fecha de inicio (si el usuario la usa)
    inicio = request.args.get('inicio')
    if inicio:
        try:
            año0_str, mes0_str = inicio.split('-')
            año0, mes0 = int(año0_str), int(mes0_str)
        except ValueError:
            pass  # Ignorar si es inválido

    # Leer disponibilidad desde la BD
    cursor.execute(
        "SELECT medico, dia FROM disponibilidad WHERE (anio = %s AND mes >= %s) OR (anio = %s AND mes < %s)",
        (año0, mes0, año0 + 1, mes0)
    )
    datos = cursor.fetchall()
    conexion.close()

    # Agrupar por weekday entero (1=lunes ... 6=sábado)
    dispo_por_weekday = {}
    for medico, wd in datos:
        try:
            wd_int = int(wd)
            if 1 <= wd_int <= 6:
                dispo_por_weekday.setdefault(wd_int, []).append(medico)
        except:
            continue

    print("→ dispo_por_weekday:", dispo_por_weekday)  # depuración

    # Pintar 4 meses
    meses = []
    for i in range(4):
        m = (mes0 - 1 + i) % 12 + 1
        y = año0 + ((mes0 - 1 + i) // 12)
        cal = calendar.Calendar()
        semanas = []
        for semana in cal.monthdayscalendar(y, m):
            semana_info = []
            for d in semana:
                if d != 0:
                    try:
                        # weekday: 0=lunes, ..., 6=domingo
                        #weekday = datetime(y, m, d).weekday()
                        #dia_dispo = weekday + 1 
                        map_python_to_bd = {0: 1, 1: 2, 2: 3, 3: 4, 4: 5, 5: 6}
                        weekday = datetime(y, m, d).weekday()
                        dia_dispo = map_python_to_bd.get(weekday, 0)
                        if dia_dispo != 0:
                            medicos = list(set(dispo_por_weekday.get(dia_dispo, [])))
                        else:
                            medicos = []

                        print(f"→ Día: {d} ({y}-{m}), weekday={weekday}, dia_dispo={dia_dispo}")  # depuración

                        if dia_dispo != 0:
                            medicos = list(set(dispo_por_weekday.get(dia_dispo, [])))
                        else:
                            medicos = []

                        semana_info.append({'dia': d, 'medicos': medicos})
                    except:
                        semana_info.append({'dia': d, 'medicos': []})
                else:
                    semana_info.append({'dia': 0, 'medicos': []})
            semanas.append(semana_info)
        meses.append({'mes': m, 'anio': y, 'semanas': semanas})
        print(f"Fecha: {d}-{m}-{y} (weekday {weekday}) → Dia_dispo: {dia_dispo} → Médicos: {medicos}")
    return render_template('multi_calendario.html', meses=meses)



@app.route('/confirmar_guardado', methods=['POST'])
def confirmar_guardado():
    nombre = request.form["nombre"]
    dni = request.form["dni"]
    fecha = request.form["fecha"]
    medico = request.form["medico"]
    proxima_fecha = request.form["proxima_fecha"]
    
    conn = conectar_bd()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO pacientes (nombre, dni, fecha, medico, proxima_fecha)
        VALUES (%s, %s, %s, %s, %s)
    """, (nombre, dni, fecha, medico, proxima_fecha))
    conn.commit()
    cursor.close()
    conn.close()

    return redirect(url_for("index", guardado=1))


@app.route('/editar_disponibilidad', methods=['GET', 'POST'])
def editar_disponibilidad():
    conexion = conectar_bd()
    cursor = conexion.cursor()

    # Lista base de médicos (por si la BD está vacía)
    medicos_base = [
        "Dr. Correa",
        "Dr. Isla",
        "Dra. Laymito",
        "Dra. Torres",
        "Dr. Figueroa"
    ]

    # Obtener mes y año actual
    hoy = datetime.now()
    mes_actual = hoy.month
    anio_actual = hoy.year

    mensaje = ""

    # Si se pidió reset (vaciar tabla)
    if 'reset' in request.args:
        cursor.execute("DELETE FROM disponibilidad WHERE mes = %s AND anio = %s", (mes_actual, anio_actual))
        conexion.commit()
        mensaje = "Disponibilidad vaciada para los próximos 4 meses."

    # Si se envió formulario POST (guardar nueva disponibilidad)
    if request.method == 'POST':
        cursor.execute("DELETE FROM disponibilidad WHERE mes = %s AND anio = %s", (mes_actual, anio_actual))

        for medico in medicos_base:
            dias_seleccionados = request.form.getlist(f"{medico}[]")
            for dia in dias_seleccionados:
                cursor.execute(
                    "INSERT INTO disponibilidad (medico, dia, mes, anio) VALUES (%s, %s, %s, %s)",
                    (medico, int(dia), mes_actual, anio_actual)
                )
        conexion.commit()
        mensaje = "✅ Disponibilidad guardada correctamente."

    # Obtener disponibilidad actual
    cursor.execute("SELECT medico, dia FROM disponibilidad WHERE mes = %s AND anio = %s", (mes_actual, anio_actual))
    datos = cursor.fetchall()

    # Construir estructuras para el HTML
    disponibilidad_actual = {}
    for medico, dia in datos:
        disponibilidad_actual.setdefault(medico, []).append(int(dia))

    disponibilidad_por_dia = {}
    for medico, dias in disponibilidad_actual.items():
        for d in dias:
            disponibilidad_por_dia.setdefault(d, []).append(medico)

    cursor.close()
    conexion.close()
    
    nombres_con_titulo = {
    "Dr. Laymito": "Dra. Laymito",
    "Dr. Correa": "Dr. Correa",
    "Dr. Julia": "Dra. Julia",
    "Dr. Isla": "Dr. Isla",
    "Dr. Figueroa": "Dr. Figueroa"
    }

    
    return render_template(
        'editar_disponibilidad.html',
        medicos=medicos_base,
        mes_actual=mes_actual,
        anio_actual=anio_actual,
        disponibilidad=disponibilidad_actual,
        disponibilidad_por_dia=disponibilidad_por_dia,
        mensaje=mensaje,
        nombres_con_titulo=nombres_con_titulo
    )



#app = Flask(__name__)
app.secret_key = 'clavesecreta'  # Cambia esto


@app.route('/login', methods=['GET', 'POST'])
def login():
    mensaje = ''
    if request.method == 'POST':
        usuario = request.form['usuario']
        contraseña = request.form['contraseña']
#        contraseña_encriptada = generate_password_hash(contraseña)

        conexion = conectar_bd()
        cursor = conexion.cursor()
        cursor.execute("SELECT * FROM usuarios WHERE username = %s AND password = %s", (usuario, contraseña))
        usuario = cursor.fetchone()
        cursor.close()
        conexion.close()

        if usuario:
            session['usuario'] = usuario[1]
            return redirect(url_for('index'))
        else:
            mensaje = '❌ Usuario o contraseña incorrectos'

    return render_template('login.html', mensaje=mensaje)

@app.route('/logout')
def logout():
    session.pop('usuario', None)
    return redirect(url_for('login'))

@app.route('/')
def index():
    if 'usuario' not in session:
        return redirect(url_for('login'))

    conexion = conectar_bd()
    cursor = conexion.cursor()
    
    hoy = datetime.now()
    mes, anio = hoy.month, hoy.year

    cursor.execute("SELECT medico, dia FROM disponibilidad WHERE mes = %s AND anio = %s", (mes, anio))
    datos = cursor.fetchall()
    conexion.close()

    global disponibilidad_medicos
    disponibilidad_medicos = {}

    for medico, dia in datos:
        if medico not in disponibilidad_medicos:
            disponibilidad_medicos[medico] = []
        disponibilidad_medicos[medico].append(dia)

    return render_template('index.html', usuario=session['usuario'], disponibilidad=disponibilidad_medicos)


#localhost
# if __name__ == '__main__':
    # app.run(debug=True ,host='0.0.0.0', port=10000)
    
# #para render
if __name__ == '__main__':
   app.run(host='0.0.0.0', port=10000)
