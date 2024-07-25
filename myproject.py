import os
import random
import secrets
import traceback
from pathlib import Path

from PIL import Image

import requests
import json
from flask import Flask, flash, abort
from flask import request, redirect, render_template, url_for, send_from_directory, session, make_response, send_file

from urllib.parse import urlencode
import urllib3
from lxml import etree
import mariadb
import sys
# pillow
import PIL
from werkzeug.utils import secure_filename

app = Flask(__name__)
SECRET_FILE_PATH = Path(".flask_secret")
try:
    with SECRET_FILE_PATH.open("r") as secret_file:
        app.secret_key = secret_file.read()
except FileNotFoundError:
    # Let's create a cryptographically secure code in that file
    with SECRET_FILE_PATH.open("w") as secret_file:
        app.secret_key = secrets.token_hex(32)
        secret_file.write(app.secret_key)
stages = ["Эксплуатируется", "Не используется", "Эксплуатация не начиналась", "Ожидание исключения", "Списан",
          "Данные неизвестны", "КВР с заменой кузова", "Перемещен в пределах города", "Отправлен в другой город",
          "Замена госномера на предприятии"]

global_database = "fotobus"
global_info = "id"


def callDB():
    try:
        conn = mariadb.connect(
            user="root",
            password="DataBasePass",
            host="localhost",
            port=3306,
            database=global_database
        )
    except mariadb.Error as e:
        print(f"Error connecting to MariaDB Platform: {e}")
        sys.exit(1)
    return conn.cursor(dictionary=True), conn


@app.route('/')
@app.route('/index')
def index():
    session['last_page'] = '/index'
    cur, con = callDB()
    cur.execute(
        """SELECT CONCAT('photos/',PHOTO_ID,PATH,'.png') AS PATH, CAST(PHOTO_ID AS CHAR) AS PHOTO_ID, PHOTO_ID AS G,
DATE_FORMAT(PUBLISHED,'%e.%m.%Y') AS PUBLISHED
FROM PHOTOS
WHERE MODERATED >= 7 
ORDER BY G DESC
LIMIT 6;""",
        (id,))
    photos = cur.fetchall()

    cur.execute(
        """SELECT COUNT(PHOTO_ID) AS A FROM PHOTOS WHERE MODERATED >=7;""")
    photo = cur.fetchone()['A']

    cur.execute(
        """SELECT COUNT(ATP_ID) AS A FROM ATPS;""")
    parks = cur.fetchone()['A']

    cur.execute(
        """SELECT COUNT(BUS_ID) AS A FROM BUSES;""")
    buses = cur.fetchone()['A']

    cur.execute(
        """SELECT COUNT(PROFILE_ID) AS A FROM PROFILES WHERE RANG >= 3;""")
    profiles = cur.fetchone()['A']

    con.close()
    return render_template('index.html', photos=photos, photo=photo, profiles=profiles - 4, parks=parks, buses=buses)


# @app.route('/mirbus')
# def mirbus():
#    return render_template('mirbus.html')


@app.route('/terms')
def terms():
    return render_template('terms.html')


@app.route('/park/<type>')
def park(type):
    park_stages = ['✅', '⛔', '❌', '🏤', '⚙', '🚍', '🛠', '🚧', '🚌', ' ', ' ', ' ']

    names = {"tram": "Городской электротранспорт: Трамваи", "troll": "Городской электротранспорт: троллейбусы",
             "mpatp": "Муниципальные автобусы", "ebus": "Городской электротранспорт: электробусы",
             "metro": "Городской электротранспорт: метро и монорельс", "plane": "Воздушный транспорт",
             "fleet": "Водный транспорт", "train": "Железнодорожная галерея Провинции",
             "atp01": "Частные автотранспортные предприятия, 1 сервер",
             "atp02": "Частные автотранспортные предприятия, 2 сервер",
             "atp03": "Частные автотранспортные предприятия, 3 сервер",
             "atp04": "Частные автотранспортные предприятия, 4 сервер",
             "atp05": "Частные автотранспортные предприятия, 5 сервер",
             "atp06": "Частные автотранспортные предприятия, 6 сервер",
             "atp07": "Частные автотранспортные предприятия, 7 сервер",
             "atp00": "Частные автотранспортные предприятия, 7 сервер"}
    if type == 'test' and (not session.get('RANG') or session.get('RANG') < 50):
        abort(403)
    names['test'] = 'Тестовые АТП'
    if not type in names.keys():
        abort(404)

    session['last_page'] = '/park/' + type
    cur, con = callDB()

    cur.execute(
        """SELECT * FROM ATPS WHERE TYPE = ?;""",
        (type,))
    atps = cur.fetchall()

    cur.execute(
        """SELECT NAME, CAST(CATS_ID AS CHAR) AS CATS_ID FROM CATS WHERE TYPE = ?;""",
        (type,))
    cats = cur.fetchall()
    con.close()
    return render_template('park.html', atps=atps, park_stages=park_stages, type=type, name=names[type], cats=cats)


@app.route('/mvps/<depo>')
def mvps(depo):
    session['last_page'] = '/mvps/' + depo
    cur, con = callDB()
    cur.execute(
        """SELECT ATP_ID, VK, ABOUT, TYPE, NAME, CITI_ROUTES, COMMUTER_ROUTES, INTERCITY_ROUTES FROM ATPS WHERE ATP_ID = ? ;""",
        (depo,))
    atp_info = cur.fetchone()

    if not atp_info:
        con.close()
        abort(404)
    if atp_info['TYPE'] == 'test' and (not session.get('RANG') or session.get('RANG') < 50):
        con.close()
        abort(403)

    okey = True
    order = request.cookies.get('sort')
    if not order:
        order = 'B'
    if not order in ['B', 'GOS_NUMBER', 'MODEL', 'M', 'S']:
        order = 'B'

    if request.cookies.get('photo') == 'with':
        cur.execute(
            """SELECT CAST(A.BUS_ID AS CHAR) AS BUS_ID, A.BUS_ID AS B, GOS_NUMBER, MODEL, A.ABOUT, PARK, A.STAGE, CAST(C.PHOTO_ID AS CHAR) AS PHOTO_ID,
DATE_FORMAT(MADE,'%m.%Y') AS MADE, MADE AS M,
DATE_FORMAT(START,'%m.%Y') AS START, START AS S,
DATE_FORMAT(END,'%m.%Y') AS END,
DATE_FORMAT(DELETED,'%m.%Y') AS DELETED
FROM BUSES A, PHOTOBUS C
WHERE A.ATP_ID = ?
AND A.BUS_ID = C.BUS_ID 
AND C.PHOTO_ID = (SELECT MAX(M.PHOTO_ID) FROM PHOTOBUS M, PHOTOS N WHERE N.PHOTO_ID = M.PHOTO_ID AND M.BUS_ID = A.BUS_ID AND N.MODERATED >= 7)
UNION 
SELECT E.BUS_ID, E.BUS_ID AS B, GOS_NUMBER, MODEL, E.ABOUT, PARK, STAGE, '0' AS PHOTO_ID,
DATE_FORMAT(MADE,'%m.%Y') AS MADE, MADE AS M,
DATE_FORMAT(START,'%m.%Y') AS START, START AS S,
DATE_FORMAT(END,'%m.%Y') AS END,
DATE_FORMAT(DELETED,'%m.%Y') AS DELETED
FROM BUSES E 
WHERE NOT EXISTS (SELECT MM.PHOTO_ID FROM PHOTOBUS MM, PHOTOS NN WHERE MM.BUS_ID = E.BUS_ID AND NN.PHOTO_ID = MM.PHOTO_ID AND NN.MODERATED >= 7)
AND E.ATP_ID = ?
ORDER BY STAGE, """ + order + """;""",
            (depo, depo))
        buses = cur.fetchall()
        if len(buses) == 0:
            okey = False
        con.close()
        if request.cookies.get('table') == 'with':
            return render_template('table_with_photo.html', buses=buses, atp=atp_info, okey=okey)
        else:
            return render_template('mvps_with_photo.html', buses=buses, atp=atp_info, okey=okey)
    else:
        cur.execute(
            """SELECT CAST(BUS_ID AS CHAR) AS BUS_ID, BUS_ID AS B, GOS_NUMBER, MODEL, ABOUT, STAGE, PARK, DATE_FORMAT(MADE,'%m.%Y') AS MADE, MADE AS M, START AS S, DATE_FORMAT(START,'%m.%Y') AS START, DATE_FORMAT(END,'%m.%Y') AS END, DATE_FORMAT(DELETED,'%m.%Y') AS DELETED FROM BUSES WHERE ATP_ID = ? ORDER BY STAGE, """ + order + """;""",
            (depo,))
        buses = cur.fetchall()
        if len(buses) == 0:
            okey = False
        con.close()
        if request.cookies.get('table') == 'with':
            return render_template('table_no_photo.html', buses=buses, atp=atp_info, okey=okey)
        else:
            return render_template('mvps_no_photo.html', buses=buses, atp=atp_info, okey=okey)


@app.route('/mvps_statistic/<depo>')
def mvps_statistic(depo):
    session['last_page'] = '/mvps/' + depo
    cur, con = callDB()
    cur.execute(
        """SELECT ATP_ID, TYPE, NAME FROM ATPS WHERE ATP_ID = ? ;""",
        (depo,))
    atp_info = cur.fetchone()

    if not atp_info:
        con.close()
        abort(404)
    if atp_info['TYPE'] == 'test' and (not session.get('RANG') or session.get('RANG') < 50):
        con.close()
        abort(403)

    okey = True

    cur.execute(
        """SELECT DISTINCT MODEL, (SELECT COUNT(BUS_ID) FROM BUSES B WHERE B.STAGE=0 AND ATP_ID= ? AND B.MODEL = A.MODEL) AS CA,
         (SELECT COUNT(BUS_ID) FROM BUSES B WHERE B.STAGE < 3 AND ATP_ID= ? AND B.MODEL = A.MODEL) AS CB FROM BUSES A WHERE ATP_ID = ? AND 
         EXISTS(SELECT BUS_ID FROM BUSES B WHERE B.STAGE < 3 AND ATP_ID= ? AND B.MODEL = A.MODEL) ORDER BY 3 DESC, 1;""",
        (depo, depo, depo, depo))
    buses = cur.fetchall()

    cur.execute(
        """SELECT DISTINCT MODEL, 
         (SELECT COUNT(BUS_ID) FROM BUSES B WHERE B.STAGE >= 3 AND ATP_ID= ? AND B.MODEL = A.MODEL) AS CB FROM BUSES A WHERE ATP_ID = ? AND 
         NOT EXISTS(SELECT BUS_ID FROM BUSES B WHERE B.STAGE < 3 AND ATP_ID= ? AND B.MODEL = A.MODEL)
          AND EXISTS(SELECT BUS_ID FROM BUSES B WHERE B.STAGE >= 3 AND ATP_ID= ? AND B.MODEL = A.MODEL) ORDER BY 1;""",
        (depo, depo, depo, depo))
    deleted = cur.fetchall()

    if len(buses) == 0:
        okey = False
    con.close()
    return render_template('mvps_statistic.html', buses=buses, atp=atp_info, okey=okey, deleted=deleted)


@app.route('/with_photo')
def with_photo():
    res = make_response(redirect(session.get('last_page') if session.get('last_page') else 'index'))
    res.set_cookie('photo', 'with', max_age=60 * 60 * 24 * 30)
    return res


@app.route('/sort/<type>')
def sort(type):
    res = make_response(redirect(session.get('last_page') if session.get('last_page') else 'index'))
    res.set_cookie('sort', type, max_age=60 * 60 * 24 * 30)
    return res


@app.route('/no_photo')
def no_photo():
    res = make_response(redirect(session.get('last_page') if session.get('last_page') else 'index'))
    res.set_cookie('photo', 'no', max_age=60 * 60 * 24 * 30)
    return res


@app.route('/with_table')
def with_table():
    res = make_response(redirect(session.get('last_page') if session.get('last_page') else 'index'))
    res.set_cookie('table', 'with', max_age=60 * 60 * 24 * 30)
    return res


@app.route('/no_table')
def no_table():
    res = make_response(redirect(session.get('last_page') if session.get('last_page') else 'index'))
    res.set_cookie('table', 'no', max_age=60 * 60 * 24 * 30)
    return res


@app.route('/test')
def test():
    return 'no' if not request.cookies.get('sort') else request.cookies.get('sort')


@app.route('/get_icon/<id>')
def get_icon(id):
    if id == '0':
        filename = 'static/photos/default_bus.jpg'
    else:
        cur, con = callDB()
        cur.execute("""SELECT CONCAT(PHOTO_ID,PATH) AS PATH FROM PHOTOS WHERE PHOTO_ID = ? AND MODERATED >=7;""",
                    (id,))
        photo = cur.fetchone()
        if not photo:
            con.close()
            abort(404)
        filename = 'static/icons/' + str(photo['PATH']) + '.jpg'
        con.close()
    return send_file(filename, mimetype='image/jpg')


@app.route('/get_icon_self/<id>')
def get_icon_self(id):
    if not session.get('PROFILE_ID'):
        return redirect('/login')
    if id == '0':
        filename = 'static/photos/default_bus.jpg'
    else:
        cur, con = callDB()
        cur.execute("""SELECT CONCAT(PHOTO_ID,PATH) AS PATH FROM PHOTOS WHERE PHOTO_ID = ? AND PROFILE_ID = ?;""",
                    (id, session.get('PROFILE_ID')))
        photo = cur.fetchone()
        if not photo:
            con.close()
            abort(404)
        filename = 'static/icons/' + str(photo['PATH']) + '.jpg'
        con.close()
    return send_file(filename, mimetype='image/jpg')


@app.route('/get_icon_power/<id>')
def get_icon_power(id):
    if not session.get('RANG') or session.get('RANG') < 40:
        abort(403)
    if id == '0':
        filename = 'static/photos/default_bus.jpg'
    else:
        cur, con = callDB()
        cur.execute("""SELECT CONCAT(PHOTO_ID,PATH) AS PATH FROM PHOTOS WHERE PHOTO_ID = ?;""",
                    (id,))
        photo = cur.fetchone()
        if not photo:
            con.close()
            abort(404)
        filename = 'static/icons/' + str(photo['PATH']) + '.jpg'
        con.close()
    return send_file(filename, mimetype='image/jpg')


@app.route('/get_photo_power/<id>')
def get_photo_power(id):
    if not session.get('RANG') or session.get('RANG') < 40:
        abort(403)
    if id == '0':
        filename = 'static/photos/default_bus.jpg'
    else:
        cur, con = callDB()
        cur.execute("""SELECT CONCAT(PHOTO_ID,PATH) AS PATH FROM PHOTOS WHERE PHOTO_ID = ?;""",
                    (id,))
        photo = cur.fetchone()
        if not photo:
            con.close()
            abort(404)
        filename = 'static/photos/' + str(photo['PATH']) + '.png'
        con.close()
    return send_file(filename, mimetype='image/png')


@app.route('/get_image/<id>')
def get_image(id):
    cur, con = callDB()
    cur.execute("""SELECT CONCAT(PHOTO_ID,PATH) AS PATH FROM PHOTOS WHERE PHOTO_ID = ? AND MODERATED >=7;""", (id,))
    photo = cur.fetchone()
    if not photo:
        con.close()
        abort(404)
    filename = 'static/photos/' + photo['PATH'] + '.png'
    con.close()
    return send_file(filename, mimetype='image/png')


@app.route('/vehicle/<id>')
def vehicle(id):
    session['last_page'] = '/vehicle/' + id
    cur, con = callDB()
    cur.execute(
        """SELECT BUSES.ATP_ID, NAME, CONCAT(', ',MODEL,' ', GOS_NUMBER) AS TITLE
        FROM BUSES, ATPS
        WHERE BUSES.ATP_ID = ATPS.ATP_ID AND BUS_ID = ?;""",
        (id,))
    title = cur.fetchone()

    if not title:
        con.close()
        abort(404)

    cur.execute(
        """SELECT BUS_ID, GOS_NUMBER, MODEL, ABOUT, STAGE, PARK,
DATE_FORMAT(MADE,'%m.%Y') AS MADE,
DATE_FORMAT(START,'%m.%Y') AS START,
DATE_FORMAT(END,'%m.%Y') AS END,
DATE_FORMAT(DELETED,'%m.%Y') AS DELETED
FROM BUSES WHERE BUS_ID = ? ;""",
        (id,))
    bus = dict()
    k = 0
    try:
        bus = dict(cur.fetchone())
        k = int(bus['STAGE'])
    except:
        pass

    cur.execute(
        """SELECT STAGE, ABOUT,
DATE_FORMAT(DAY,'%e.%m.%Y') AS SCRINED
FROM EVENTS
WHERE BUS_ID = ?
ORDER BY SCRINED DESC;""",
        (id,))
    events = cur.fetchall()

    cur.execute(
        """SELECT PHOTOS.SCRINED AS T, TITLE, STAGE, ROUTE, NICK, CAST(PHOTOS.PHOTO_ID AS CHAR) AS PHOTO_ID, DATE_FORMAT(SCRINED,'%e.%m.%Y') AS SCRINED, PROFILES.PROFILE_ID
FROM PHOTOS, PROFILES, PHOTOBUS
WHERE PHOTOBUS.PHOTO_ID = PHOTOS.PHOTO_ID AND PHOTOBUS.BUS_ID = ? AND MODERATED >=7 AND PROFILES.PROFILE_ID=PHOTOS.PROFILE_ID AND RANG >= 7
UNION
SELECT PHOTOS.SCRINED AS T, TITLE, STAGE, ROUTE, 'by инкогнито' AS NICK, CAST(PHOTOS.PHOTO_ID AS CHAR) AS PHOTO_ID, DATE_FORMAT(SCRINED,'%e.%m.%Y') AS SCRINED, 4 AS PROFILE_ID
FROM PHOTOS, PROFILES, PHOTOBUS
WHERE PHOTOBUS.PHOTO_ID = PHOTOS.PHOTO_ID AND PHOTOBUS.BUS_ID = ? AND MODERATED >=7 AND PROFILES.PROFILE_ID=PHOTOS.PROFILE_ID AND RANG < 7
ORDER BY 1 DESC;""",
        (id, id,))
    photos = cur.fetchall()
    con.close()
    return render_template('vehicle.html', title=title, bus=bus, events=events, photos=photos, stage=stages[k])


@app.route('/kategory/<id>')
def kategory(id):
    session['last_page'] = '/kategory/' + id
    cur, con = callDB()
    cur.execute(
        """SELECT NAME, CATS_ID FROM CATS WHERE CATS_ID = ?;""",
        (id,))
    title = cur.fetchone()

    if not title:
        con.close()
        abort(404)

    cur.execute(
        """SELECT PHOTOS.PHOTO_ID AS T, TITLE, STAGE, NICK, CAST(PHOTOS.PHOTO_ID AS CHAR) AS PHOTO_ID, DATE_FORMAT(SCRINED,'%e.%m.%Y') AS SCRINED, PROFILES.PROFILE_ID
FROM PHOTOS, PROFILES, PHOTOCATS
WHERE PHOTOCATS.PHOTO_ID = PHOTOS.PHOTO_ID AND PHOTOCATS.CATS_ID = ? AND MODERATED >=7 AND PROFILES.PROFILE_ID=PHOTOS.PROFILE_ID AND RANG >= 7
UNION
SELECT PHOTOS.PHOTO_ID AS T, TITLE, STAGE, 'by инкогнито' AS NICK, CAST(PHOTOS.PHOTO_ID AS CHAR) AS PHOTO_ID, DATE_FORMAT(SCRINED,'%e.%m.%Y') AS SCRINED, 4 AS PROFILE_ID
FROM PHOTOS, PROFILES, PHOTOCATS
WHERE PHOTOCATS.PHOTO_ID = PHOTOS.PHOTO_ID AND PHOTOCATS.CATS_ID = ? AND MODERATED >=7 AND PROFILES.PROFILE_ID=PHOTOS.PROFILE_ID AND RANG < 7
ORDER BY 1 DESC;""",
        (id, id,))
    photos = cur.fetchall()
    con.close()
    return render_template('kategory.html', title=title, photos=photos)


@app.route('/photos')
def photos():
    # session['last_page'] = '/vehicle/' + id
    #
    # AND NOT EXISTS(SELECT BUS_ID FROM PHOTOBUS WHERE PHOTOBUS.PHOTO_ID=PHOTOS.PHOTO_ID)
    #    AND EXISTS(SELECT CATS_ID FROM PHOTOCATS WHERE PHOTOCATS.PHOTO_ID=PHOTOS.PHOTO_ID);""")
    cur, con = callDB()

    cur.execute(
        """SELECT PHOTO_ID AS A, TITLE, PHOTOS.STAGE, NICK, CAST(PHOTOS.PHOTO_ID AS CHAR) AS PHOTO_ID, DATE_FORMAT(SCRINED,'%e.%m.%Y') AS SCRINED, PROFILES.PROFILE_ID,
        (SELECT MAX(CONCAT('B;',PHOTOBUS.BUS_ID,';',GOS_NUMBER,';',MODEL)) FROM PHOTOBUS, BUSES WHERE PHOTOBUS.PHOTO_ID = PHOTOS.PHOTO_ID AND PHOTOBUS.BUS_ID=BUSES.BUS_ID) AS INFO
FROM PHOTOS, PROFILES
WHERE MODERATED >=7 AND PROFILES.PROFILE_ID=PHOTOS.PROFILE_ID AND RANG >= 7 AND EXISTS(SELECT BUS_ID FROM PHOTOBUS WHERE PHOTOBUS.PHOTO_ID=PHOTOS.PHOTO_ID)
UNION
SELECT PHOTO_ID AS A, TITLE, PHOTOS.STAGE, NICK, CAST(PHOTOS.PHOTO_ID AS CHAR) AS PHOTO_ID, DATE_FORMAT(SCRINED,'%e.%m.%Y') AS SCRINED, PROFILES.PROFILE_ID,
        (SELECT MAX(CONCAT('C;',PHOTOCATS.CATS_ID,';',NAME)) FROM PHOTOCATS, CATS WHERE PHOTOCATS.PHOTO_ID = PHOTOS.PHOTO_ID AND PHOTOCATS.CATS_ID=CATS.CATS_ID) AS INFO
FROM PHOTOS, PROFILES
WHERE MODERATED >=7 AND PROFILES.PROFILE_ID=PHOTOS.PROFILE_ID AND RANG >= 7 AND NOT EXISTS(SELECT BUS_ID FROM PHOTOBUS WHERE PHOTOBUS.PHOTO_ID=PHOTOS.PHOTO_ID)
AND EXISTS(SELECT CATS_ID FROM PHOTOCATS WHERE PHOTOCATS.PHOTO_ID=PHOTOS.PHOTO_ID) ORDER BY 1 DESC LIMIT 30; """)
    photos = cur.fetchall()
    con.close()
    return render_template('photos.html', photos=photos)


@app.route('/myphotos')
def myphotos():
    if not session.get('PROFILE_ID'):
        return redirect('/login')
    # session['last_page'] = '/vehicle/' + id
    cur, con = callDB()
    marks = {0: "Отклонено", 2: "Был заблокирован", 3: "Не оценено", 7: "К- И-", 8: "К0 И-", 9: "К+ И-", 10: "К- И0",
             11: "К0 И0",
             12: "К+ И0", 14: "К0 И+", 15: "К+ И+", 16: "Оценка для неавторских"}

    cur.execute(
        """SELECT PHOTO_ID AS A, TITLE, PHOTOS.STAGE, COMMENT, MODERATED, NICK, CAST(PHOTOS.PHOTO_ID AS CHAR) AS PHOTO_ID, DATE_FORMAT(SCRINED,'%e.%m.%Y') AS SCRINED, PROFILES.PROFILE_ID,
        (SELECT MAX(CONCAT('B;',PHOTOBUS.BUS_ID,';',GOS_NUMBER,';',MODEL)) FROM PHOTOBUS, BUSES WHERE PHOTOBUS.PHOTO_ID = PHOTOS.PHOTO_ID AND PHOTOBUS.BUS_ID=BUSES.BUS_ID) AS INFO
FROM PHOTOS, PROFILES
WHERE MODERATED >=7 AND ISAUTHOR = 1 AND PROFILES.PROFILE_ID = ? AND PROFILES.PROFILE_ID=PHOTOS.PROFILE_ID AND RANG >= 7 AND EXISTS(SELECT BUS_ID FROM PHOTOBUS WHERE PHOTOBUS.PHOTO_ID=PHOTOS.PHOTO_ID)
UNION
SELECT PHOTO_ID AS A, TITLE, PHOTOS.STAGE, COMMENT, MODERATED, NICK, CAST(PHOTOS.PHOTO_ID AS CHAR) AS PHOTO_ID, DATE_FORMAT(SCRINED,'%e.%m.%Y') AS SCRINED, PROFILES.PROFILE_ID,
        (SELECT MAX(CONCAT('C;',PHOTOCATS.CATS_ID,';',NAME)) FROM PHOTOCATS, CATS WHERE PHOTOCATS.PHOTO_ID = PHOTOS.PHOTO_ID AND PHOTOCATS.CATS_ID=CATS.CATS_ID) AS INFO
FROM PHOTOS, PROFILES
WHERE MODERATED >=7 AND ISAUTHOR = 1 AND PROFILES.PROFILE_ID = ? AND PROFILES.PROFILE_ID=PHOTOS.PROFILE_ID AND RANG >= 7 AND NOT EXISTS(SELECT BUS_ID FROM PHOTOBUS WHERE PHOTOBUS.PHOTO_ID=PHOTOS.PHOTO_ID)
AND EXISTS(SELECT CATS_ID FROM PHOTOCATS WHERE PHOTOCATS.PHOTO_ID=PHOTOS.PHOTO_ID) ORDER BY 1 DESC LIMIT 30; """,
        (session.get('PROFILE_ID'), session.get('PROFILE_ID'),))
    photos = cur.fetchall()
    con.close()
    return render_template('myphotos.html', photos=photos, marks=marks)


@app.route('/photo/<id>', methods=['GET', 'POST'])
def photo(id):
    session['last_page'] = '/photo/' + id
    cur, con = callDB()
    cur.execute(
        """SELECT TITLE, CAST(PHOTO_ID AS CHAR) AS PHOTO_ID, PHOTOS.ABOUT AS PHOTOABOUT, NICK, ISAUTHOR, ISAI,
DATE_FORMAT(SCRINED,'%e.%m.%Y') AS SCRINED, PROFILES.PROFILE_ID
FROM PHOTOS, PROFILES
WHERE PHOTO_ID= ? AND PHOTOS.PROFILE_ID = PROFILES.PROFILE_ID AND MODERATED >=7 AND PROFILES.RANG>=7
UNION
SELECT TITLE, CAST(PHOTO_ID AS CHAR) AS PHOTO_ID, PHOTOS.ABOUT AS PHOTOABOUT, 'by инкогнито' AS NICK, ISAUTHOR, ISAI,
DATE_FORMAT(SCRINED,'%e.%m.%Y') AS SCRINED, 4 AS PROFILE_ID
FROM PHOTOS, PROFILES
WHERE PHOTO_ID= ? AND PHOTOS.PROFILE_ID = PROFILES.PROFILE_ID AND MODERATED >=7 AND PROFILES.RANG<7;""",
        (id, id))
    photo = cur.fetchone()

    if not photo:
        con.close()
        if session.get('RANG') and session.get('RANG') >= 50:
            return redirect('/photomoderation')
        abort(404)

    cur.execute(
        """SELECT ROUTE, CAST(PHOTO_ID AS CHAR) AS PHOTO_ID, GOS_NUMBER, PHOTOBUS.BUS_ID, MODEL, BUSES.ATP_ID, ATPS.NAME
        FROM PHOTOBUS, BUSES, ATPS
WHERE PHOTOBUS.PHOTO_ID= ? AND PHOTOBUS.BUS_ID = BUSES.BUS_ID AND ATPS.ATP_ID = BUSES.ATP_ID;""",
        (id,))
    routes = cur.fetchall()

    cur.execute(
        """SELECT CAST(PHOTO_ID AS CHAR) AS PHOTO_ID, NAME, CAST(PHOTOCATS.CATS_ID AS CHAR) AS CATS_ID
        FROM PHOTOCATS, CATS
        WHERE PHOTOCATS.PHOTO_ID = ? AND PHOTOCATS.CATS_ID = CATS.CATS_ID;""",
        (id,))
    cats = cur.fetchall()

    cur.execute("""SELECT COUNT(CREATED) AS ANS FROM LIKES WHERE PHOTO_ID = ? ;""", (id,))
    ans = cur.fetchone()
    if ans['ANS'] > 0:
        likes = '+' + str(ans['ANS'])
    else:
        likes = '0'

    if session.get("PROFILE_ID"):
        cur.execute("""SELECT COUNT(CREATED) AS ANS FROM LIKES WHERE PROFILE_ID = ? AND PHOTO_ID = ?;""",
                    (session.get("PROFILE_ID"), id,))
        ans = cur.fetchone()
        if ans['ANS'] == 0:
            liked = False
        else:
            liked = True
    else:
        liked = False

    if request.method == 'POST':
        if session.get("PROFILE_ID"):
            cur.execute(
                """INSERT INTO `fotobus`.`LIKES` (`PHOTO_ID`, `PROFILE_ID`, `CREATED`) VALUES (?, ?, CURRENT_DATE());""",
                (id, session.get("PROFILE_ID"),))
            con.commit()
            con.close()
        return redirect(session['last_page'])
    else:
        con.close()
        return render_template('photo.html', photo=photo, likes=likes, liked=liked, routes=routes, cats=cats)



@app.route('/login')
def login():
    #Должен выполняться запрос к VH Outh 2.0, но ключи приложения удалены в рамках безопасности
    login_link = '/auth'
    return render_template('login.html', link=login_link)


@app.route('/auth', methods=['GET'])
def auth():
    x_forwarded_for = request.headers.get('X-Forwarded-For', '').split(',')
    client_ip = x_forwarded_for[0] if x_forwarded_for[0] != '' else request.headers.get('X-Real-IP',
                                                                                        request.remote_addr)
    session['IP'] = client_ip

    y = {'id' : 348066085, 'first_name' : 'Алексей'}

    cur, con = callDB()
    cur.execute("""SELECT COUNT(PROFILE_ID) AS ANS FROM PROFILES WHERE VKID = ? ;""", (y['id'],))
    ans = cur.fetchone()

    cur.execute("""INSERT INTO LOGINS (VKID, IP, T) VALUES (?, ?, CURRENT_TIMESTAMP);""", (y['id'], client_ip))
    con.commit()
    if ans['ANS'] == 1:
        cur.execute("""SELECT PROFILE_ID, NICK, RANG, VKID FROM PROFILES WHERE VKID = ? ;""", (y['id'],))
        ans = cur.fetchone()
        if ans['RANG'] >= 40:
            cur.execute(
                """INSERT INTO LOGS (PROFILE_ID, DID, DONE, VKID, IP) VALUES (?, CURRENT_TIMESTAMP(), 'Авторизовался на сайте', ?, ?);""",
                (ans['PROFILE_ID'], session.get('VKID'), session.get('IP')))
            con.commit()

        con.close()

        if ans['RANG'] <= 2:
            return "Вам запрещено изменять контент на нашем сайте"
        else:
            session['RANG'] = ans['RANG']
            session['NICK'] = ans['NICK']
            session['PROFILE_ID'] = ans['PROFILE_ID']
            session['VKID'] = ans['VKID']
            return redirect(session.get('last_page') if session.get('last_page') else '/index')

    else:
        con.close()
        session['VKID'] = y['id']
        session['NAME'] = y['first_name']
        return redirect('/reg')


@app.route('/myprofile')
def myprofile():
    if not session.get('PROFILE_ID'):
        return redirect('/login')
    cur, con = callDB()
    cur.execute(
        """SELECT NAME, PROFILE_ID, BUS, VKID, NICK, SHOWVK, ABOUT, NICKNAME, RANG FROM PROFILES WHERE PROFILE_ID = ? ;""",
        (session.get('PROFILE_ID'),))
    profile = cur.fetchone()

    cur.execute(
        """SELECT COUNT(PHOTO_ID) AS A FROM PHOTOS WHERE MODERATED <= 3 AND PUBLISHED = CURRENT_DATE() AND PROFILE_ID = ?;""",
        (session.get('PROFILE_ID'),))
    aa = cur.fetchone()['A']

    cur.execute(
        """SELECT PHOTOS.STAGE, TITLE, ROUTE, PHOTOS.ABOUT, NICK, CAST(PHOTOS.PHOTO_ID AS CHAR) AS PHOTO_ID,
DATE_FORMAT(SCRINED,'%e.%m.%Y') AS SCRINED, DATE_FORMAT(PUBLISHED,'%e.%m.%Y') AS PUBLISHED, ISAUTHOR, ISAI, CAST(PHOTOBUS.BUS_ID AS CHAR) AS BUS_ID, GOS_NUMBER, MODEL
FROM PHOTOS, PROFILES, BUSES, PHOTOBUS
WHERE PHOTOBUS.PHOTO_ID=PHOTOS.PHOTO_ID AND BUSES.BUS_ID=PHOTOBUS.BUS_ID AND PROFILES.PROFILE_ID = ? AND MODERATED = 3 AND PROFILES.PROFILE_ID=PHOTOS.PROFILE_ID
ORDER BY SCRINED DESC;""",
        (session.get('PROFILE_ID'),))
    photos = cur.fetchall()

    cur.execute(
        """SELECT PHOTOS.STAGE, TITLE, PHOTOS.ABOUT, NICK, CAST(PHOTOS.PHOTO_ID AS CHAR) AS PHOTO_ID,
DATE_FORMAT(SCRINED,'%e.%m.%Y') AS SCRINED, DATE_FORMAT(PUBLISHED,'%e.%m.%Y') AS PUBLISHED, ISAUTHOR, ISAI, CAST(PHOTOCATS.CATS_ID AS CHAR) AS CATS_ID, CATS.NAME
FROM PHOTOS, PROFILES, PHOTOCATS, CATS
WHERE PHOTOCATS.PHOTO_ID=PHOTOS.PHOTO_ID AND CATS.CATS_ID=PHOTOCATS.CATS_ID AND PROFILES.PROFILE_ID = ? AND MODERATED = 3 AND PROFILES.PROFILE_ID=PHOTOS.PROFILE_ID
ORDER BY SCRINED DESC;""",
        (session.get('PROFILE_ID'),))
    cats = cur.fetchall()

    cur.execute(
        """SELECT PHOTOS.STAGE AS PHOTOSTAGE, TITLE, PHOTOS.ABOUT AS PHOTOABOUT, NICK, CAST(PHOTOS.PHOTO_ID AS CHAR) AS PHOTO_ID,
DATE_FORMAT(SCRINED,'%e.%m.%Y') AS SCRINED, DATE_FORMAT(PUBLISHED,'%e.%m.%Y') AS PUBLISHED, ISAUTHOR, ISAI,
GOS_NUMBER, MODEL, START, END, DELETED, MADE, PARK, FAKEBUSES.STAGE AS BUSSTAGE, FAKEBUSES.ABOUT AS BUSABOUT, ATP_ID, FAKEBUS_ID
FROM PHOTOS, PROFILES, FAKEBUSES
WHERE FAKEBUSES.PHOTO_ID=PHOTOS.PHOTO_ID AND PROFILES.PROFILE_ID = ? AND FAKEBUSES.MARK = 0 AND PROFILES.PROFILE_ID=PHOTOS.PROFILE_ID
ORDER BY SCRINED DESC;""",
        (session.get('PROFILE_ID'),))
    buses = cur.fetchall()

    con.close()
    return render_template('myprofile.html', profile=profile, photos=photos, cats=cats, buses=buses, aa=aa)


@app.route('/profile/<id>')
def profile(id):
    cur, con = callDB()
    cur.execute(
        """SELECT NAME, PROFILE_ID, BUS, VKID, NICK, SHOWVK, ABOUT, NICKNAME, RANG FROM PROFILES WHERE RANG >= 7 AND PROFILE_ID = ? ;""",
        (id,))
    profile = cur.fetchone()

    if not profile:
        con.close()
        abort(404)

    cur.execute(
        """SELECT PHOTO_ID AS A, TITLE, PHOTOS.STAGE, NICK, CAST(PHOTOS.PHOTO_ID AS CHAR) AS PHOTO_ID, DATE_FORMAT(SCRINED,'%e.%m.%Y') AS SCRINED, PROFILES.PROFILE_ID,
        (SELECT MAX(CONCAT('B;',PHOTOBUS.BUS_ID,';',GOS_NUMBER,';',MODEL)) FROM PHOTOBUS, BUSES WHERE PHOTOBUS.PHOTO_ID = PHOTOS.PHOTO_ID AND PHOTOBUS.BUS_ID=BUSES.BUS_ID) AS INFO
FROM PHOTOS, PROFILES
WHERE MODERATED >=7 AND ISAUTHOR = 1 AND PROFILES.PROFILE_ID = ? AND PROFILES.PROFILE_ID=PHOTOS.PROFILE_ID AND RANG >= 7 AND EXISTS(SELECT BUS_ID FROM PHOTOBUS WHERE PHOTOBUS.PHOTO_ID=PHOTOS.PHOTO_ID)
UNION
SELECT PHOTO_ID AS A, TITLE, PHOTOS.STAGE, NICK, CAST(PHOTOS.PHOTO_ID AS CHAR) AS PHOTO_ID, DATE_FORMAT(SCRINED,'%e.%m.%Y') AS SCRINED, PROFILES.PROFILE_ID,
        (SELECT MAX(CONCAT('C;',PHOTOCATS.CATS_ID,';',NAME)) FROM PHOTOCATS, CATS WHERE PHOTOCATS.PHOTO_ID = PHOTOS.PHOTO_ID AND PHOTOCATS.CATS_ID=CATS.CATS_ID) AS INFO
FROM PHOTOS, PROFILES
WHERE MODERATED >=7 AND ISAUTHOR = 1 AND PROFILES.PROFILE_ID = ? AND PROFILES.PROFILE_ID=PHOTOS.PROFILE_ID AND RANG >= 7 AND NOT EXISTS(SELECT BUS_ID FROM PHOTOBUS WHERE PHOTOBUS.PHOTO_ID=PHOTOS.PHOTO_ID)
AND EXISTS(SELECT CATS_ID FROM PHOTOCATS WHERE PHOTOCATS.PHOTO_ID=PHOTOS.PHOTO_ID) ORDER BY 1 DESC LIMIT 30; """,
        (id, id,))
    photos = cur.fetchall()

    cur.execute(
        """SELECT COUNT(PHOTO_ID) AS A FROM PHOTOS WHERE MODERATED >=7 AND PROFILE_ID = ?;""", (id,))
    photo = cur.fetchone()['A']

    con.close()
    return render_template('profile.html', profile=profile, photo=photo, photos=photos)


@app.route('/edit_profile')
def edit_profile():
    if not session.get('PROFILE_ID'):
        return redirect('/login')
    cur, con = callDB()
    cur.execute(
        """SELECT NAME, PROFILE_ID, BUS, NICK, SHOWVK, ABOUT, NICKNAME, RANG FROM PROFILES WHERE PROFILE_ID = ? ;""",
        (session.get('PROFILE_ID'),))
    profile = cur.fetchone()
    con.close()
    return render_template('edit_profil.html', profile=profile)


@app.route('/edit_my_photo', methods=['POST'])
def edit_my_photo():
    if not session.get('PROFILE_ID'):
        return redirect('/login')
    cur, con = callDB()
    cur.execute(
        """SELECT * FROM PHOTOS WHERE MODERATED=3 AND PROFILE_ID = ? AND PHOTO_ID = ?;""",
        (session.get('PROFILE_ID'), request.form.get('photo')))
    photo = cur.fetchone()
    con.close()
    stages_new = [{'i': i, 'stage': stages[i]} for i in range(0, 10)]
    return render_template('edit_my_photo.html', photo=photo, stages=stages_new)


@app.route('/edit_my_photo_form', methods=['POST'])
def edit_my_photo_form():
    if not session.get('PROFILE_ID'):
        return redirect('/login')
    cur, con = callDB()

    args = (request.form.get('title'), request.form.get('about'),
            request.form.get('scrined'),
            request.form.get('stage'), request.form.get('isauthor'), request.form.get('isai'),
            session.get('PROFILE_ID'), request.form.get('photo'),)
    cur.execute(
        """UPDATE PHOTOS SET TITLE =?, ABOUT=?, SCRINED=?, STAGE=?, ISAUTHOR=?, ISAI=?, MARK=3, ADM=5 WHERE MODERATED=3 AND PROFILE_ID=? AND PHOTO_ID=?;""",
        args
    )

    args = (session.get('VKID'), str(request.form.get('photo')) + str(request.form.get('path')),
            request.form.get('title') + str(request.form.get('scrined')),
            request.form.get('about'), session.get('IP'))

    cur.execute(
        """INSERT INTO ARCHIVE (VKID, FIELDA, FIELDB, FIELDC, T, IP) VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP(), ?);""",
        args
    )

    con.commit()
    con.close()
    return redirect('/myprofile')


@app.route('/edit_photo_power', methods=['POST'])
def edit_photo_power():
    if not session.get('RANG') or session.get('RANG') < 50:
        abort(403)
    cur, con = callDB()
    cur.execute(
        """SELECT * FROM PHOTOS WHERE PHOTO_ID = ?;""",
        (request.form.get('photo'),))
    photo = cur.fetchone()

    cur.execute(
        """SELECT ROUTE, CAST(PHOTO_ID AS CHAR) AS PHOTO_ID, GOS_NUMBER, PHOTOBUS.BUS_ID, MODEL, BUSES.ATP_ID, ATPS.NAME
        FROM PHOTOBUS, BUSES, ATPS
WHERE PHOTOBUS.PHOTO_ID= ? AND PHOTOBUS.BUS_ID = BUSES.BUS_ID AND ATPS.ATP_ID = BUSES.ATP_ID;""",
        (request.form.get('photo'),))
    routes = cur.fetchall()

    cur.execute(
        """SELECT CAST(PHOTO_ID AS CHAR) AS PHOTO_ID, NAME, CAST(PHOTOCATS.CATS_ID AS CHAR) AS CATS_ID
        FROM PHOTOCATS, CATS
        WHERE PHOTOCATS.PHOTO_ID = ? AND PHOTOCATS.CATS_ID = CATS.CATS_ID;""",
        (request.form.get('photo'),))
    cats = cur.fetchall()

    con.close()
    stages_new = [{'i': i, 'stage': stages[i]} for i in range(0, 10)]

    marks = {0: "Отклонено", 2: "Был заблокирован", 3: "Не оценено", 7: "К- И-", 8: "К0 И-", 9: "К+ И-", 10: "К- И0",
             11: "К0 И0",
             12: "К+ И0", 14: "К0 И+", 15: "К+ И+", 16: "Оценка для неавторских"}
    values = marks.keys()
    return render_template('edit_photo_power.html', photo=photo, stages=stages_new, marks=marks, values=values,
                           routes=routes, cats=cats)


@app.route('/edit_photo_power_form', methods=['POST'])
def edit_photo_power_form():
    if not session.get('RANG') or session.get('RANG') < 50:
        abort(403)
    cur, con = callDB()

    args = (request.form.get('title'), request.form.get('about'),
            request.form.get('scrined'),
            request.form.get('stage'), request.form.get('isauthor'), request.form.get('isai'),
            request.form.get('comment'),
            request.form.get('photo'),)
    cur.execute(
        """UPDATE PHOTOS SET TITLE =?, ABOUT=?, SCRINED=?, STAGE=?, ISAUTHOR=?, ISAI=?, COMMENT=? WHERE PHOTO_ID=?;""",
        args
    )

    cur.execute(
        """INSERT INTO LOGS (PROFILE_ID, DID, DONE, MARK, NEWA, NEWB, VKID, IP) VALUES (?, CURRENT_TIMESTAMP(), 'Отредактировал фото', 5, ?, ?, ?, ?);""",
        (session.get('PROFILE_ID'),

         request.form.get('photo') + request.form.get('title') + request.form.get('scrined') + request.form.get(
             'stage') + request.form.get('isauthor') + request.form.get('isai') + request.form.get(
             'comment')

         , request.form.get('about'), session.get('VKID'), session.get('IP')))

    con.commit()
    con.close()
    return redirect('/photo/' + str(request.form.get('photo')))


@app.route('/delete_photobus_form', methods=['POST'])
def delete_photobus_form():
    if not session.get('RANG') or session.get('RANG') < 50:
        abort(403)
    cur, con = callDB()

    args = (request.form.get('photo'), request.form.get('bus'))
    cur.execute(
        """DELETE FROM PHOTOBUS WHERE PHOTO_ID=? AND BUS_ID=?;""",
        args
    )

    con.commit()
    con.close()
    return redirect('/photo/' + str(request.form.get('photo')))


@app.route('/delete_photocats_form', methods=['POST'])
def delete_photocats_form():
    if not session.get('RANG') or session.get('RANG') < 50:
        abort(403)
    cur, con = callDB()

    args = (request.form.get('photo'), request.form.get('cats'))
    cur.execute(
        """DELETE FROM PHOTOCATS WHERE PHOTO_ID=? AND CATS_ID=?;""",
        args
    )

    con.commit()
    con.close()
    return redirect('/photo/' + str(request.form.get('photo')))


@app.route('/add_photocats_form', methods=['POST'])
def add_photocats_form():
    if not session.get('RANG') or session.get('RANG') < 50:
        abort(403)
    cur, con = callDB()

    args = (request.form.get('photo'), request.form.get('cats'))
    cur.execute(
        """INSERT INTO PHOTOCATS (PHOTO_ID, CATS_ID) VALUES (?, ?);""",
        args
    )

    con.commit()
    con.close()
    return redirect('/photo/' + str(request.form.get('photo')))


@app.route('/add_photobus_form', methods=['POST'])
def add_photobus_form():
    if not session.get('RANG') or session.get('RANG') < 50:
        abort(403)
    cur, con = callDB()

    args = (request.form.get('photo'), request.form.get('bus'), request.form.get('route'))
    cur.execute(
        """INSERT INTO PHOTOBUS (PHOTO_ID, BUS_ID, ROUTE) VALUES (?, ?, ?);""",
        args
    )

    cur.execute(
        """INSERT INTO LOGS (PROFILE_ID, DID, DONE, MARK, NEWA, VKID, IP) VALUES (?, CURRENT_TIMESTAMP(), 'Привязал фото к ПС', 5, ?, ?, ?);""",
        (session.get('PROFILE_ID'),
         request.form.get('photo') + " " + request.form.get('bus') + " " + request.form.get('route'),
         session.get('VKID'), session.get('IP')))

    con.commit()
    con.close()
    return redirect('/photo/' + str(request.form.get('photo')))


@app.route('/edit_profil_form', methods=['POST'])
def edit_profil_form():
    if not session.get('PROFILE_ID'):
        return redirect('/login')
    if session.get('RANG') < 10:
        new_rang = 5
    else:
        new_rang = session.get('RANG')

    cur, con = callDB()
    cur.execute(
        """UPDATE PROFILES SET BUS = ?, SHOWVK = ?, NICKNAME = ?, NAME = ?, NICK = ?, ABOUT = ?, RANG = ? WHERE PROFILE_ID = ?;""",
        (request.form.get('bus'), request.form.get('vkshow'), request.form.get('nickname'), request.form.get('name'),
         request.form.get('nick'), request.form.get('about'), new_rang, session.get('PROFILE_ID'),))

    args = (session.get('VKID'), request.form.get('nick') + request.form.get('name') + request.form.get('bus'),
            request.form.get('nickname'),
            request.form.get('about'), session.get('IP'))
    cur.execute(
        """INSERT INTO ARCHIVE (VKID, FIELDA, FIELDB, FIELDC, T, IP) VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP(), ?);""",
        args
    )

    con.commit()
    con.close()
    return redirect('/myprofile')


@app.route('/reg')
def reg():
    if not session.get('VKID'):
        return redirect('/login')
    names = ["Трамвайщик", "Троллейбусник", "Водитель", "Вагоноважатый", "Метрофанат"]
    nick = random.choice(names) + str(random.randint(10, 99))
    return render_template('reg.html', name=session.get("NAME"), nick=nick)


@app.route('/reg_form', methods=['POST'])
def reg_form():
    if not session.get('VKID'):
        return redirect('/login')
    cur, con = callDB()
    cur.execute(
        """INSERT INTO PROFILES
(REGISTER, RANG, VKID, NAME, NICK, SHOWVK, BUS, ABOUT, NICKNAME)
VALUES
(CURRENT_DATE(), ?, ?, ?, ?, ?, ?, ?, ?) RETURNING PROFILE_ID, NICK, RANG;""",
        (5, session.get('VKID'), request.form.get('name'), request.form.get('nick'), request.form.get('vkshow'),
         request.form.get('bus'),
         request.form.get('about'), request.form.get('nickname'),))
    user = cur.fetchone()

    args = (session.get('VKID'), request.form.get('nick') + request.form.get('name') + request.form.get('bus'),
            request.form.get('nickname'),
            request.form.get('about'), session.get('IP'))
    cur.execute(
        """INSERT INTO ARCHIVE (VKID, FIELDA, FIELDB, FIELDC, T, IP) VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP(), ?);""",
        args
    )

    con.commit()
    session['RANG'] = user['RANG']
    session['NICK'] = user['NICK']
    session['PROFILE_ID'] = user['PROFILE_ID']
    con.close()
    return redirect('/myprofile')


@app.route('/logout')
def logout():
    session.pop('PROFILE_ID')
    session.pop('RANG')
    session.pop('NICK')
    return redirect('/index')


@app.route('/jour')
def jour():
    if not session.get('RANG') or session.get('RANG') < 40:
        abort(403)

    cur, con = callDB()
    cur.execute(
        """SELECT COUNT(PROFILE_ID) AS A FROM PROFILES WHERE RANG=5;""")
    profiles = cur.fetchone()['A']

    cur.execute(
        """SELECT COUNT(FAKEBUS_ID) AS A FROM FAKEBUSES WHERE MARK=0;""")
    buses = cur.fetchone()['A']

    cur.execute(
        """SELECT COUNT(PHOTO_ID) AS A FROM PHOTOS WHERE MODERATED=3 AND (EXISTS(SELECT PHOTO_ID FROM PHOTOBUS WHERE PHOTOBUS.PHOTO_ID=PHOTOS.PHOTO_ID) OR EXISTS(SELECT PHOTO_ID FROM PHOTOCATS WHERE PHOTOCATS.PHOTO_ID=PHOTOS.PHOTO_ID));""")
    photos = cur.fetchone()['A']

    con.close()
    return render_template('jour.html', profiles=profiles, buses=buses, photos=photos)


@app.route('/load')
def load():
    if not session.get('RANG') or session.get('RANG') < 90:
        abort(403)
    return render_template('load.html')


@app.route('/verification')
def verefication():
    if not session.get('RANG') or session.get('RANG') < 50:
        abort(403)
    cur, con = callDB()
    cur.execute(
        """SELECT NAME, NICK, BUS, VKID, ABOUT, PROFILE_ID, NICKNAME FROM PROFILES WHERE RANG=5;""")
    users = cur.fetchall()
    con.close()
    return render_template('verification.html', users=users)


@app.route('/logs')
def logs():
    if not session.get('RANG') or session.get('RANG') < 40:
        abort(403)
    cur, con = callDB()
    cur.execute(
        """SELECT NICK, DID, DONE, OLDA, OLDB, OLDC, NEWA, NEWB, NEWC FROM LOGS, PROFILES
        WHERE LOGS.PROFILE_ID=PROFILES.PROFILE_ID AND DATE(DID)=CURRENT_DATE();""")
    users = cur.fetchall()
    con.close()
    return render_template('logs.html', users=users)


@app.route('/reset/<id>')
def reset(id):
    if not session.get('RANG') or session.get('RANG') < 90:
        abort(404)
    cur, con = callDB()
    cur.execute(
        """SELECT NAME, NICK, BUS, VKID, ABOUT, PROFILE_ID, NICKNAME FROM PROFILES WHERE PROFILE_ID=?;""", (id,))
    users = cur.fetchone()
    con.close()
    return render_template('reset.html', user=users)


@app.route('/profiles')
def profiles():
    if not session.get('RANG') or session.get('RANG') < 50:
        abort(403)
    cur, con = callDB()
    cur.execute(
        """SELECT NICK, PROFILE_ID, RANG, REGISTER FROM PROFILES ORDER BY PROFILE_ID DESC;""")
    users = cur.fetchall()
    con.close()
    return render_template('profiles.html', users=users)


@app.route('/photomoderation')
def photomoderation():
    if not session.get('RANG') or session.get('RANG') < 40:
        abort(403)
    marks = {0: "Отклонено", 3: "Не оценено", 7: "К- И-", 8: "К0 И-", 9: "К+ И-", 10: "К- И0", 11: "К0 И0",
             12: "К+ И0", 14: "К0 И+", 15: "К+ И+", 16: "Оценка для неавторских"}
    values = marks.keys()
    cur, con = callDB()
    cur.execute(
        """SELECT CAST(PHOTOS.PHOTO_ID AS CHAR) AS PHOTO_ID, PHOTOS.PROFILE_ID, PUBLISHED, TITLE, PHOTOS.ABOUT AS PHOTOABOUT, ROUTE, SCRINED, PHOTOS.STAGE, ISAUTHOR, ISAI, PHOTOBUS.BUS_ID, GOS_NUMBER, MODEL, VKID, NICK, NAME, NICKNAME, REGISTER, BUS, PROFILES.ABOUT AS PROFILEABOUT, MARK, CAST(ADM AS CHAR) AS ADM, COMMENT
        FROM PHOTOS, PHOTOBUS, PROFILES, BUSES
        WHERE PHOTOBUS.PHOTO_ID=PHOTOS.PHOTO_ID AND PHOTOBUS.BUS_ID = BUSES.BUS_ID AND PROFILES.PROFILE_ID = PHOTOS.PROFILE_ID AND MODERATED=3;""")
    users = cur.fetchall()

    cur.execute(
        """SELECT CAST(PHOTOS.PHOTO_ID AS CHAR) AS PHOTO_ID, PHOTOS.PROFILE_ID, PUBLISHED, TITLE, PHOTOS.ABOUT AS PHOTOABOUT, SCRINED, PHOTOS.STAGE, ISAUTHOR, ISAI, CAST(PHOTOCATS.CATS_ID AS CHAR) AS CATS_ID, CATS.NAME, VKID, NICK, CATS.NAME, NICKNAME, REGISTER, BUS, PROFILES.ABOUT AS PROFILEABOUT, MARK, CAST(ADM AS CHAR) AS ADM, COMMENT
        FROM PHOTOS, PHOTOCATS, PROFILES, CATS
        WHERE PHOTOCATS.PHOTO_ID=PHOTOS.PHOTO_ID AND PHOTOCATS.CATS_ID = CATS.CATS_ID AND PROFILES.PROFILE_ID = PHOTOS.PROFILE_ID AND MODERATED=3;""")
    cats = cur.fetchall()
    con.close()
    return render_template('photo_moderation.html', users=users, marks=marks, values=values, cats=cats)


@app.route('/busmoderation')
def busmoderation():
    if not session.get('RANG') or session.get('RANG') < 50:
        abort(403)
    marks = {0: "Отклонено", 2: "Был заблокирован", 7: "К- И-", 8: "К0 И-", 9: "К+ И-", 10: "К- И0", 11: "К0 И0",
             12: "К+ И0", 14: "К0 И+", 15: "К+ И+", 16: "Оценка для неавторских"}
    values = marks.keys()
    cur, con = callDB()
    cur.execute(
        """SELECT PHOTOS.STAGE AS PHOTOSTAGE, TITLE, PHOTOS.ABOUT AS PHOTOABOUT, NICK, CAST(PHOTOS.PHOTO_ID AS CHAR) AS PHOTO_ID,
DATE_FORMAT(SCRINED,'%e.%m.%Y') AS SCRINED, DATE_FORMAT(PUBLISHED,'%e.%m.%Y') AS PUBLISHED, ISAUTHOR, ISAI,
GOS_NUMBER, MODEL, START, END, DELETED, MADE, PARK, FAKEBUSES.STAGE AS BUSSTAGE, FAKEBUSES.ABOUT AS BUSABOUT, ATP_ID, FAKEBUS_ID,
PROFILES.ABOUT AS PROFILEABOUT, NAME, VKID, NICKNAME, BUS
FROM PHOTOS, PROFILES, FAKEBUSES
WHERE FAKEBUSES.PHOTO_ID=PHOTOS.PHOTO_ID AND FAKEBUSES.MARK = 0 AND PROFILES.PROFILE_ID=PHOTOS.PROFILE_ID
ORDER BY SCRINED DESC;""")
    users = cur.fetchall()

    con.close()
    return render_template('bus_moderation.html', users=users, marks=marks, values=values)


@app.route('/busmoderation_bad')
def busmoderation_bad():
    if not session.get('RANG') or session.get('RANG') < 50:
        abort(403)
    marks = {0: "Отклонено", 2: "Был заблокирован", 7: "К- И-", 8: "К0 И-", 9: "К+ И-", 10: "К- И0", 11: "К0 И0",
             12: "К+ И0", 14: "К0 И+", 15: "К+ И+", 16: "Оценка для неавторских"}
    values = marks.keys()
    cur, con = callDB()
    cur.execute(
        """SELECT PHOTOS.STAGE AS PHOTOSTAGE, TITLE, PHOTOS.ABOUT AS PHOTOABOUT, NICK, CAST(PHOTOS.PHOTO_ID AS CHAR) AS PHOTO_ID,
DATE_FORMAT(SCRINED,'%e.%m.%Y') AS SCRINED, DATE_FORMAT(PUBLISHED,'%e.%m.%Y') AS PUBLISHED, ISAUTHOR, ISAI,
GOS_NUMBER, MODEL, START, END, DELETED, MADE, PARK, FAKEBUSES.STAGE AS BUSSTAGE, FAKEBUSES.ABOUT AS BUSABOUT, ATP_ID, FAKEBUS_ID,
PROFILES.ABOUT AS PROFILEABOUT, NAME, VKID, NICKNAME, BUS
FROM PHOTOS, PROFILES, FAKEBUSES
WHERE FAKEBUSES.PHOTO_ID=PHOTOS.PHOTO_ID AND FAKEBUSES.MARK = 2 AND PROFILES.PROFILE_ID=PHOTOS.PROFILE_ID
ORDER BY SCRINED DESC;""")
    users = cur.fetchall()

    con.close()
    return render_template('bus_moderation.html', users=users, marks=marks, values=values)


@app.route('/photomoderation_bad')
def photomoderation_bad():
    if not session.get('RANG') or session.get('RANG') < 40:
        abort(403)
    marks = {0: "Отклонено", 2: "Был заблокирован", 7: "К- И-", 8: "К0 И-", 9: "К+ И-", 10: "К- И0", 11: "К0 И0",
             12: "К+ И0", 14: "К0 И+", 15: "К+ И+", 16: "Оценка для неавторских"}
    values = marks.keys()
    cur, con = callDB()
    cur.execute(
        """SELECT CAST(PHOTOS.PHOTO_ID AS CHAR) AS PHOTO_ID, PUBLISHED, TITLE, PHOTOS.ABOUT AS PHOTOABOUT, ROUTE, SCRINED, PHOTOS.STAGE, ISAUTHOR, ISAI, PHOTOBUS.BUS_ID, GOS_NUMBER, MODEL, VKID, NICK, NAME, NICKNAME, REGISTER, BUS, PROFILES.ABOUT AS PROFILEABOUT,  MARK, CAST(ADM AS CHAR) AS ADM, COMMENT
        FROM PHOTOS, PHOTOBUS, PROFILES, BUSES
        WHERE PHOTOBUS.PHOTO_ID=PHOTOS.PHOTO_ID AND PHOTOBUS.BUS_ID = BUSES.BUS_ID AND PROFILES.PROFILE_ID = PHOTOS.PROFILE_ID AND MODERATED IN (0, 2);""")
    users = cur.fetchall()

    cur.execute(
        """SELECT CAST(PHOTOS.PHOTO_ID AS CHAR) AS PHOTO_ID, PUBLISHED, TITLE, PHOTOS.ABOUT AS PHOTOABOUT, SCRINED, PHOTOS.STAGE, ISAUTHOR, ISAI, CAST(PHOTOCATS.CATS_ID AS CHAR) AS CATS_ID, CATS.NAME, VKID, NICK, CATS.NAME, NICKNAME, REGISTER, BUS, PROFILES.ABOUT AS PROFILEABOUT,  MARK, CAST(ADM AS CHAR) AS ADM, COMMENT
        FROM PHOTOS, PHOTOCATS, PROFILES, CATS
        WHERE PHOTOCATS.PHOTO_ID=PHOTOS.PHOTO_ID AND PHOTOCATS.CATS_ID = CATS.CATS_ID AND PROFILES.PROFILE_ID = PHOTOS.PROFILE_ID AND MODERATED IN (0, 2);""")
    cats = cur.fetchall()
    con.close()
    return render_template('photo_moderation_bad.html', users=users, marks=marks, values=values, cats=cats)


@app.route('/photomoderation_lost')
def photomoderation_lost():
    if not session.get('RANG') or session.get('RANG') < 50:
        abort(403)
    marks = {0: "Отклонено", 2: "Был заблокирован", 7: "К- И-", 8: "К0 И-", 9: "К+ И-", 10: "К- И0", 11: "К0 И0",
             12: "К+ И0", 14: "К0 И+", 15: "К+ И+", 16: "Оценка для неавторских"}
    values = marks.keys()
    cur, con = callDB()
    cur.execute(
        """SELECT CAST(PHOTO_ID AS CHAR) AS PHOTO_ID, PUBLISHED, TITLE, PHOTOS.ABOUT AS PHOTOABOUT, SCRINED, PHOTOS.STAGE, ISAUTHOR, ISAI, VKID, NICK, NAME, NICKNAME, REGISTER, BUS, PROFILES.ABOUT AS PROFILEABOUT, MARK, CAST(ADM AS CHAR) AS ADM, COMMENT
        FROM PHOTOS, PROFILES
        WHERE PROFILES.PROFILE_ID = PHOTOS.PROFILE_ID AND MODERATED >= 7
        AND NOT EXISTS(SELECT BUS_ID FROM PHOTOBUS WHERE PHOTOBUS.PHOTO_ID=PHOTOS.PHOTO_ID)
        AND NOT EXISTS(SELECT CATS_ID FROM PHOTOCATS WHERE PHOTOCATS.PHOTO_ID=PHOTOS.PHOTO_ID);""")

    users = cur.fetchall()
    con.close()
    return render_template('photo_moderation.html', users=users, marks=marks, values=values)


@app.route('/change_akk', methods=['POST'])
def change_akk():
    if not session.get('RANG') or session.get('RANG') < 50:
        abort(403)
    cur, con = callDB()
    cur.execute(
        """UPDATE PROFILES SET RANG = ? WHERE PROFILE_ID = ?;""",
        (min(int(request.form.get('new_rang')), 7), request.form.get('akk')))
    cur.execute(
        """SELECT * FROM PROFILES WHERE PROFILE_ID = ?;""",
        (request.form.get('akk'),))
    atp = cur.fetchone()
    cur.execute(
        """INSERT INTO LOGS (PROFILE_ID, DID, DONE, MARK, NEWA, NEWB, NEWC, VKID, IP) VALUES (?, CURRENT_TIMESTAMP(), 'Верифицировал пользователя', 0, ?, ?, ?, ?, ?);""",
        (session.get('PROFILE_ID'),
         request.form.get('new_rang') + atp['NICK'] + atp['NAME'] + atp['BUS'], atp['ABOUT'], atp['NICKNAME'],
         session.get('VKID'), session.get('IP')))

    con.commit()
    con.close()
    return redirect('/jour')


@app.route('/ban_akk', methods=['POST'])
def ban_akk():
    if not session.get('RANG') or session.get('RANG') < 40:
        abort(403)
    cur, con = callDB()
    cur.execute(
        """UPDATE PROFILES SET RANG = 1 WHERE PROFILE_ID = ?;""",
        (request.form.get('akk'),))
    cur.execute(
        """SELECT * FROM PROFILES WHERE PROFILE_ID = ?;""",
        (request.form.get('akk'),))
    atp = cur.fetchone()

    cur.execute(
        """INSERT INTO LOGS (PROFILE_ID, DID, DONE, MARK, NEWA, NEWB, NEWC, VKID, IP) VALUES (?, CURRENT_TIMESTAMP(), 'Заблоикровал пользователя', 0, ?, ?, ?, ?, ?);""",
        (session.get('PROFILE_ID'),
         atp['NICK'] + atp['NAME'] + atp['BUS'], atp['ABOUT'], atp['NICKNAME'], session.get('VKID'), session.get('IP')))

    con.commit()
    con.close()
    return redirect('/jour')


@app.route('/change_akk_hard', methods=['POST'])
def change_akk_hard():
    if not session.get('RANG') or session.get('RANG') < 90:
        abort(404)
    cur, con = callDB()
    cur.execute(
        """UPDATE PROFILES SET RANG = ? WHERE PROFILE_ID = ?;""",
        (request.form.get('new_rang'), request.form.get('akk')))
    con.commit()
    con.close()
    return redirect('/profiles')


@app.route('/addBus')
def addBus():
    if not session.get('RANG') or session.get('RANG') < 50:
        abort(403)

    cur, con = callDB()
    cur.execute("""SELECT ATP_ID FROM ATPS;""")
    atps = cur.fetchall()

    cur.execute("""SELECT * FROM MODELS ORDER BY TYPE, MODEL;""")
    models = cur.fetchall()

    stages_new = [{'i': i, 'stage': stages[i]} for i in range(0, 10)]
    con.close()
    return render_template('addBus.html', atps=atps, stages=stages_new, models=models)


@app.route('/edit_atp', methods=['POST'])
def edit_atp():
    park_stages = ['✅ (работает)', '⛔ (временно не работает)', '❌ (закрылось)', '🏤 (музей)', '⚙ (завод)',
                   '🚍 (старая нумерация)', '🛠 (строится)', '🚧 (нереализованный проект)', '🚌 (частные автобусы)',
                   '- (резерв)', ' ', ' ']
    stages_new = [{'i': i, 'stage': park_stages[i]} for i in range(0, 10)]

    types = ['tram', 'troll', 'mpatp', 'ebus', 'metro', 'plane', 'fleet', 'train', 'atp01', 'atp02', 'atp03', 'atp04',
             'atp05',
             'atp06', 'atp07', 'atp00', 'test']
    if not session.get('RANG') or session.get('RANG') < 50:
        abort(403)

    cur, con = callDB()
    cur.execute(
        """SELECT * FROM ATPS WHERE ATP_ID = ?;""",
        (request.form.get('atp_id'),))
    atp = cur.fetchone()

    con.close()
    return render_template('edit_atp.html', atp=atp, stages=stages_new, types=types)


@app.route('/add_cat')
def add_cat():
    types = ['tram', 'troll', 'mpatp', 'ebus', 'metro', 'plane', 'fleet', 'train', 'atp01', 'atp02', 'atp03', 'atp04',
             'atp05',
             'atp06', 'atp07', 'atp00', 'test']
    if not session.get('RANG') or session.get('RANG') < 50:
        abort(403)
    return render_template('add_cat.html', types=types)


@app.route('/edit_bus', methods=['POST'])
def edit_bus():
    if not session.get('RANG') or session.get('RANG') < 50:
        abort(403)

    cur, con = callDB()
    cur.execute(
        """SELECT ATP_ID FROM ATPS;""",
        (id,))
    atps = cur.fetchall()

    cur, con = callDB()
    cur.execute(
        """SELECT * FROM BUSES WHERE BUS_ID = ?;""",
        (request.form.get('bus'),))
    bus = cur.fetchone()

    cur.execute("""SELECT * FROM MODELS ORDER BY TYPE, MODEL;""")
    models = cur.fetchall()

    stages_new = [{'i': i, 'stage': stages[i]} for i in range(0, 10)]
    con.close()
    return render_template('edit_bus.html', atps=atps, stages=stages_new, bus=bus, models=models)


@app.route('/edit_my_bus', methods=['POST'])
def edit_my_bus():
    if not session.get('RANG') or session.get('RANG') < 7:
        return redirect('/login')

    cur, con = callDB()
    atps = [{'ATP_ID': 'privat0' + str(i), 'NAME': 'Личные автобусы ' + str(i) + ' сервера'} for i in range(1, 8)]

    cur.execute("""SELECT * FROM MODELS WHERE TYPE=1 ORDER BY MODEL;""")
    models = cur.fetchall()

    if session.get('RANG') >= 50:
        cur.execute(
            """SELECT * FROM FAKEBUSES WHERE FAKEBUS_ID = ?;""",
            (request.form.get('bus'),))
        bus = cur.fetchone()
    else:
        cur.execute(
            """SELECT * FROM FAKEBUSES WHERE MARK=0 AND PROFILE_ID = ? AND FAKEBUS_ID = ?;""",
            (session.get('PROFILE_ID'), request.form.get('bus'),))
        bus = cur.fetchone()

    stages_new = [{'i': i, 'stage': stages[i]} for i in range(0, 10)]
    con.close()
    return render_template('edit_my_bus.html', atps=atps, stages=stages_new, bus=bus, models=models)


@app.route('/add_bus_form', methods=['POST'])
def add_bus_form():
    if not session.get('RANG') or session.get('RANG') < 50:
        abort(403)
    cur, con = callDB()
    if str(request.form.get('made')) == '':
        made = '0000-00-00'
    else:
        made = str(request.form.get('made'))
    if str(request.form.get('start')) == '':
        start = '0000-00-00'
    else:
        start = str(request.form.get('start'))
    if str(request.form.get('end')) == '':
        end = '0000-00-00'
    else:
        end = str(request.form.get('end'))
    if str(request.form.get('deleted')) == '':
        deleted = '0000-00-00'
    else:
        deleted = str(request.form.get('deleted'))
    if str(request.form.get('trans')) == '':
        trans = '0000-00-00'
    else:
        trans = str(request.form.get('trans'))

    args1 = (
        request.form.get('number'), request.form.get('stage'), request.form.get('model'), made,
        start, end, deleted,
        request.form.get('about'),
        request.form.get('park'), request.form.get('atp'))

    cur.execute(
        """INSERT INTO BUSES
    (GOS_NUMBER, STAGE, MODEL, MADE, START, END, DELETED, ABOUT, PARK, ATP_ID)
    VALUES
    (?, ?, ?, ?, ?, ?, ?, ?, ?, ?) RETURNING BUS_ID;""", args1)

    bus = cur.fetchone()
    if trans != '0000-00-00':
        cur.execute(
            """INSERT INTO EVENTS (DAY, ABOUT, BUS_ID, STAGE) VALUES (?, 'Поступил на предприятие' , ?, 2);""",
            (trans, bus['BUS_ID']))

    cur.execute(
        """INSERT INTO LOGS (PROFILE_ID, DID, DONE, MARK, NEWA, NEWB, VKID, IP) VALUES (?, CURRENT_TIMESTAMP(), 'Cоздал ПС', 5, ?, ?, ?, ?);""",
        (session.get('PROFILE_ID'),
         request.form.get('number') + request.form.get('stage') + request.form.get('model') + made +
         start + end + deleted + request.form.get('park') + request.form.get('atp'), request.form.get('about'),
         session.get('VKID'), session.get('IP')))

    con.commit()
    con.close()
    return "okey"


@app.route('/edit_bus_form', methods=['POST'])
def edit_bus_form():
    if not session.get('RANG') or session.get('RANG') < 50:
        abort(403)
    cur, con = callDB()

    if str(request.form.get('made')) == '':
        made = '0000-00-00'
    else:
        made = str(request.form.get('made'))
    if str(request.form.get('start')) == '':
        start = '0000-00-00'
    else:
        start = str(request.form.get('start'))
    if str(request.form.get('end')) == '':
        end = '0000-00-00'
    else:
        end = str(request.form.get('end'))
    if str(request.form.get('deleted')) == '':
        deleted = '0000-00-00'
    else:
        deleted = str(request.form.get('deleted'))

    args1 = (
        request.form.get('number'), request.form.get('stage'), request.form.get('model'), made,
        start, end, deleted,
        request.form.get('about'),
        request.form.get('park'), request.form.get('atp'), request.form.get('bus'))

    cur.execute(
        """UPDATE BUSES SET GOS_NUMBER=?, STAGE=?, MODEL=?, MADE=?, START=?, END=?, DELETED=?, ABOUT=?, PARK=?, ATP_ID=? WHERE BUS_ID=?;""",
        args1)

    cur.execute(
        """INSERT INTO LOGS (PROFILE_ID, DID, DONE, MARK, NEWA, NEWB, VKID, IP) VALUES (?, CURRENT_TIMESTAMP(), 'Отредактировал ПС', 5, ?, ?, ?, ?);""",
        (session.get('PROFILE_ID'),
         request.form.get('bus') + request.form.get('number') + request.form.get('stage') + request.form.get(
             'model') + made +
         start + end + deleted + request.form.get('park') + request.form.get('atp'), request.form.get('about'),
         session.get('VKID'), session.get('IP')))

    con.commit()
    con.close()
    return "okey"


@app.route('/edit_my_bus_form', methods=['POST'])
def edit_my_bus_form():
    if not session.get('RANG') or session.get('RANG') < 7:
        return redirect('/login')
    cur, con = callDB()

    if str(request.form.get('made')) == '':
        made = '0000-00-00'
    else:
        made = str(request.form.get('made'))
    if str(request.form.get('start')) == '':
        start = '0000-00-00'
    else:
        start = str(request.form.get('start'))
    if str(request.form.get('end')) == '':
        end = '0000-00-00'
    else:
        end = str(request.form.get('end'))
    if str(request.form.get('deleted')) == '':
        deleted = '0000-00-00'
    else:
        deleted = str(request.form.get('deleted'))

    args1 = (
        request.form.get('number'), request.form.get('stage'), request.form.get('model'), made,
        start, end, deleted,
        request.form.get('about'),
        request.form.get('park'), request.form.get('atp'), request.form.get('bus'), session.get('PROFILE_ID'))
    args2 = (
        request.form.get('number'), request.form.get('stage'), request.form.get('model'), made,
        start, end, deleted,
        request.form.get('about'),
        request.form.get('park'), request.form.get('atp'), request.form.get('bus'))

    if session.get('RANG') > 50:
        cur.execute(
            """UPDATE FAKEBUSES SET GOS_NUMBER=?, STAGE=?, MODEL=?, MADE=?, START=?, END=?, DELETED=?, ABOUT=?, PARK=?, ATP_ID=? WHERE FAKEBUS_ID=?;""",
            args2)

        cur.execute(
            """INSERT INTO LOGS (PROFILE_ID, DID, DONE, MARK, NEWA, NEWB, VKID, IP) VALUES (?, CURRENT_TIMESTAMP(), 'Отреда пред ПС', 5, ?, ?, ?, ?);""",
            (session.get('PROFILE_ID'),
             request.form.get('bus') + request.form.get('number') + request.form.get('stage') + request.form.get(
                 'model') + made +
             start + end + deleted + request.form.get('park') + request.form.get('atp'), request.form.get('about'),
             session.get('VKID'), session.get('IP')))
    else:
        cur.execute(
            """UPDATE FAKEBUSES SET GOS_NUMBER=?, STAGE=?, MODEL=?, MADE=?, START=?, END=?, DELETED=?, ABOUT=?, PARK=?, ATP_ID=? WHERE FAKEBUS_ID=? AND PROFILE_ID=? AND MARK=0;""",
            args1)

        args = (session.get('VKID'), request.form.get('number') + request.form.get('model'),
                made + start + end + deleted + request.form.get('park'),
                request.form.get('about_bus'), session.get('IP'))
        cur.execute(
            """INSERT INTO ARCHIVE (VKID, FIELDA, FIELDB, FIELDC, T, IP) VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP(), ?);""",
            args
        )

    con.commit()
    con.close()
    if session.get('RANG') > 50:
        return redirect('/busmoderation')
    else:
        return redirect('/myprofile')


@app.route('/edit_atp_form', methods=['POST'])
def edit_atp_form():
    if not session.get('RANG') or session.get('RANG') < 50:
        abort(403)
    cur, con = callDB()
    args1 = (
        request.form.get('new_atp_id'), request.form.get('name'), request.form.get('about'), request.form.get('city'),
        request.form.get('commuter'), request.form.get('intercity'), request.form.get('vk'), request.form.get('type'),
        request.form.get('stage'), request.form.get('old_atp_id'))

    cur.execute(
        """SELECT * FROM ATPS WHERE ATP_ID = ?;""",
        (request.form.get('old_atp_id'),))
    atp = cur.fetchone()

    cur.execute(
        """UPDATE ATPS SET ATP_ID=?, NAME=?, ABOUT=?, CITI_ROUTES=?, COMMUTER_ROUTES=?, INTERCITY_ROUTES=?, VK=?, TYPE=?, STAGE=? WHERE ATP_ID=?;""",
        args1)

    cur.execute(
        """INSERT INTO LOGS (PROFILE_ID, DID, DONE, MARK, OLDA, OLDB, OLDC, NEWA, NEWB, NEWC, VKID, IP) VALUES (?, CURRENT_TIMESTAMP(), 'Отредактировал АТП', 0, ?,?,?,?, ?, ?, ?, ?);""",
        (session.get('PROFILE_ID'), atp['ATP_ID'] + atp['VK'] + atp['TYPE'] + atp['NAME'] + str(atp['STAGE']),
         atp['CITI_ROUTES'] + atp['COMMUTER_ROUTES'] + atp['INTERCITY_ROUTES'], atp['ABOUT'],

         request.form.get('new_atp_id') + request.form.get('name') + str(request.form.get('stage')) + request.form.get(
             'city'),
         request.form.get('commuter') + request.form.get('intercity') + request.form.get('vk') + request.form.get(
             'type'),
         request.form.get('about'), session.get('VKID'), session.get('IP')))

    con.commit()
    con.close()
    return redirect('/mvps/' + request.form.get('new_atp_id'))


@app.route('/add_cat_form', methods=['POST'])
def add_cat_form():
    if not session.get('RANG') or session.get('RANG') < 50:
        abort(403)
    cur, con = callDB()
    args1 = (request.form.get('name'), request.form.get('type'))

    cur.execute(
        """INSERT INTO CATS (NAME, TYPE) VALUES (?, ?);""",
        args1)

    cur.execute(
        """INSERT INTO LOGS (PROFILE_ID, DID, DONE, MARK, NEWA, VKID, IP) VALUES (?, CURRENT_TIMESTAMP(), 'Cоздал категорию фото', 5, ?, ?, ?);""",
        (session.get('PROFILE_ID'),
         request.form.get('name') + request.form.get('type'), session.get('VKID'), session.get('IP')))

    con.commit()
    con.close()
    return redirect('/park/' + request.form.get('type'))


@app.route('/addPark', methods=['GET'])
def add_park():
    if not session.get('RANG') or session.get('RANG') < 50:
        abort(403)
    cur, con = callDB()
    a = random.randint(1000, 5000)
    args1 = (a,)

    cur.execute(
        """INSERT INTO ATPS VALUES (?, 'АТП', 'Парк создан, теперь отредактируйте его', '', '', '', '', 'test', '0');""",
        args1)

    con.commit()
    con.close()
    return redirect('/mvps/' + str(a))


@app.route('/delete_bus_form', methods=['POST'])
def delete_bus_form():
    if not session.get('RANG') or session.get('RANG') < 50:
        abort(403)
    cur, con = callDB()

    cur.execute(
        """DELETE FROM BUSES WHERE BUS_ID=?;""", (request.form.get('bus'),))

    cur.execute(
        """INSERT INTO LOGS (PROFILE_ID, DID, DONE, MARK, OLDA, VKID, IP) VALUES (?, CURRENT_TIMESTAMP(), 'Удалил ПС', 0, ?, ?, ?);""",
        (session.get('PROFILE_ID'),
         request.form.get('bus'), session.get('VKID'), session.get('IP')))

    cur.execute("COMMIT;")
    con.close()
    return redirect('/jour')


@app.route('/delete_cat_form', methods=['POST'])
def delete_cat_form():
    if not session.get('RANG') or session.get('RANG') < 50:
        abort(403)
    cur, con = callDB()

    cur.execute(
        """DELETE FROM CATS WHERE CATS_ID=?;""", (request.form.get('bus'),))

    cur.execute(
        """INSERT INTO LOGS (PROFILE_ID, DID, DONE, MARK, OLDA, VKID, IP) VALUES (?, CURRENT_TIMESTAMP(), 'Удалил категорию фото', 0, ?, ?, ?);""",
        (session.get('PROFILE_ID'),
         request.form.get('bus'), session.get('VKID'), session.get('IP')))

    cur.execute("COMMIT;")
    con.close()
    return redirect('/jour')


@app.route('/add_photo', methods=['POST', 'GET'])
def add_photo():
    if not session.get('RANG') or session.get('RANG') < 7:
        return redirect('/login')
    if not request.form.get('bus'):
        return redirect('/index')
    cur, con = callDB()

    cur.execute(
        """SELECT COUNT(PHOTO_ID) AS A FROM PHOTOS WHERE MODERATED <= 3 AND PUBLISHED = CURRENT_DATE() AND PROFILE_ID = ?;""",
        (session.get('PROFILE_ID'),))
    aa = cur.fetchone()['A']

    con.close()

    if aa >= 3 and session.get('RANG') < 10:
        return "Сегодня Вы уже загрузили 3 фотографии, пожалуйста, дождитесь, пока их проверят"
    info = {'BUS_ID': request.form.get('bus')}
    stages_new = [{'i': i, 'stage': stages[i]} for i in range(0, 10)]

    return render_template('add_photo.html', info=info, stages=stages_new)


@app.route('/add_my_bus')
def add_my_bus():
    if not session.get('RANG') or session.get('RANG') < 7:
        return redirect('/login')
    cur, con = callDB()

    cur.execute(
        """SELECT COUNT(PHOTO_ID) AS A FROM PHOTOS WHERE MODERATED <= 3 AND PUBLISHED = CURRENT_DATE() AND PROFILE_ID = ?;""",
        (session.get('PROFILE_ID'),))
    aa = cur.fetchone()['A']

    cur.execute("""SELECT * FROM MODELS WHERE TYPE = 1 ORDER BY MODEL;""")
    models = cur.fetchall()

    con.close()

    if aa >= 3 and session.get('RANG') < 10:
        return "Сегодня Вы уже загрузили 3 фотографии, пожалуйста, дождитесь, пока их проверят"

    stages_new = [{'i': i, 'stage': stages[i]} for i in range(0, 10)]
    atps = [{'ATP_ID': 'privat0' + str(i), 'NAME': 'Личные автобусы ' + str(i) + ' сервера'} for i in range(1, 8)]

    return render_template('add_my_bus.html', atps=atps, stages=stages_new, models=models)


@app.route('/add_photo_cat', methods=['POST', 'GET'])
def add_photo_cat():
    if not session.get('RANG') or session.get('RANG') < 7:
        return redirect('/login')
    if not request.form.get('bus'):
        return redirect('/index')
    cur, con = callDB()

    cur.execute(
        """SELECT COUNT(PHOTO_ID) AS A FROM PHOTOS WHERE MODERATED <= 3 AND PUBLISHED = CURRENT_DATE() AND PROFILE_ID = ?;""",
        (session.get('PROFILE_ID'),))
    aa = cur.fetchone()['A']

    con.close()

    if aa >= 3 and session.get('RANG') < 10:
        return "Сегодня Вы уже загрузили 3 фотографии, пожалуйста, дождитесь, пока их проверят"
    info = {'BUS_ID': request.form.get('bus')}
    stages_new = [{'i': i, 'stage': stages[i]} for i in range(0, 10)]

    return render_template('add_photo_cat.html', info=info, stages=stages_new)


@app.route('/add_photo_form', methods=['POST', 'GET'])
def add_photo_form():
    if not session.get('RANG') or session.get('RANG') < 7:
        return redirect('/login')

    cur, con = callDB()

    cur.execute(
        """SELECT COUNT(PHOTO_ID) AS A FROM PHOTOS WHERE MODERATED <= 3 AND PUBLISHED = CURRENT_DATE() AND PROFILE_ID = ?;""",
        (session.get('PROFILE_ID'),))
    aa = cur.fetchone()['A']

    con.close()

    if aa >= 3 and session.get('RANG') < 10:
        return "limit photo", 499

    if 'photo' not in request.files:
        return "bad photo", 498
    file = request.files['photo']
    if file.filename == '':
        return "bad photo", 498
    if len(file.filename.split('.')) == 0:
        return "bad photo", 498
    if file.filename.split('.')[-1] != 'png':
        return "bad photo", 498
    if file:
        path = str(random.randint(1000, 9999))

        cur, con = callDB()
        args = (
            path, request.form.get('title'), request.form.get('about'),
            request.form.get('scrined'), request.form.get('stage'), request.form.get('isauthor'),
            request.form.get('isai'), session.get('PROFILE_ID'),)
        cur.execute(
            """INSERT INTO PHOTOS
    (PATH, TITLE, ABOUT, SCRINED, PUBLISHED, MODERATED, STAGE, ISAUTHOR, ISAI, PROFILE_ID)
    VALUES
    (?, ?, ?, ?, CURRENT_DATE(), 3, ?, ?, ?, ?) RETURNING PHOTO_ID;""", args
        )
        photo_id = cur.fetchone()['PHOTO_ID']

        file.save(os.path.join('static/photos', str(photo_id) + path + '.png'))
        # file.save(os.path.join('static/icons', str(photo_id) + path + '.jpg'))

        # try:

        image = Image.open(os.path.join('static/photos', str(photo_id) + path + '.png'))
        rgb_im = image.convert('RGB')
        width, height = rgb_im.size
        rgb_im.thumbnail((500, int(500 * height / width)))
        rgb_im.save(os.path.join('static/icons', str(photo_id) + path + '.jpg'), quality='web_high')

        args = (session.get('VKID'), str(photo_id) + path,
                request.form.get('title') + request.form.get('route') + str(request.form.get('scrined')),
                request.form.get('about'), session.get('IP'))
        cur.execute(
            """INSERT INTO ARCHIVE (VKID, FIELDA, FIELDB, FIELDC, T, IP) VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP(), ?);""",
            args
        )

        args = (photo_id, request.form.get('bus'), request.form.get('route'))
        cur.execute(
            """INSERT INTO PHOTOBUS (PHOTO_ID, BUS_ID, ROUTE) VALUES (?, ?, ?);""",
            args
        )

        con.commit()
        con.close()

        return "okey", 200
    return "unexceptionerror", 500


@app.route('/add_my_bus_form', methods=['POST', 'GET'])
def add_my_bus_form():
    if not session.get('RANG') or session.get('RANG') < 7:
        return redirect('/login')

    cur, con = callDB()

    cur.execute(
        """SELECT COUNT(PHOTO_ID) AS A FROM PHOTOS WHERE MODERATED <= 3 AND PUBLISHED = CURRENT_DATE() AND PROFILE_ID = ?;""",
        (session.get('PROFILE_ID'),))
    aa = cur.fetchone()['A']

    con.close()

    if aa >= 3 and session.get('RANG') < 10:
        return "limit photo", 499

    if 'photo' not in request.files:
        return "bad photo", 498
    file = request.files['photo']
    if file.filename == '':
        return "bad photo", 498
    if len(file.filename.split('.')) == 0:
        return "bad photo", 498
    if file.filename.split('.')[-1] != 'png':
        return "bad photo", 498
    if file:
        path = str(random.randint(1000, 9999))

        cur, con = callDB()
        args = (
            path, request.form.get('title'), request.form.get('about'),
            request.form.get('scrined'), request.form.get('stage'), request.form.get('isauthor'),
            request.form.get('isai'), session.get('PROFILE_ID'),)
        cur.execute(
            """INSERT INTO PHOTOS
    (PATH, TITLE, ABOUT, SCRINED, PUBLISHED, MODERATED, STAGE, ISAUTHOR, ISAI, PROFILE_ID)
    VALUES
    (?, ?, ?, ?, CURRENT_DATE(), 3, ?, ?, ?, ?) RETURNING PHOTO_ID;""", args
        )
        photo_id = cur.fetchone()['PHOTO_ID']

        file.save(os.path.join('static/photos', str(photo_id) + path + '.png'))
        # file.save(os.path.join('static/icons', str(photo_id) + path + '.jpg'))

        # try:

        image = Image.open(os.path.join('static/photos', str(photo_id) + path + '.png'))
        rgb_im = image.convert('RGB')
        width, height = rgb_im.size
        rgb_im.thumbnail((500, int(500 * height / width)))
        rgb_im.save(os.path.join('static/icons', str(photo_id) + path + '.jpg'), quality='web_high')

        args = (session.get('VKID'), str(photo_id) + path,
                request.form.get('title') + str(request.form.get('scrined')),
                request.form.get('about'), session.get('IP'))
        cur.execute(
            """INSERT INTO ARCHIVE (VKID, FIELDA, FIELDB, FIELDC, T, IP) VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP(), ?);""",
            args
        )

        if str(request.form.get('made')) == '':
            made = '0000-00-00'
        else:
            made = str(request.form.get('made'))
        if str(request.form.get('start')) == '':
            start = '0000-00-00'
        else:
            start = str(request.form.get('start'))
        if str(request.form.get('end')) == '':
            end = '0000-00-00'
        else:
            end = str(request.form.get('end'))
        if str(request.form.get('deleted')) == '':
            deleted = '0000-00-00'
        else:
            deleted = str(request.form.get('deleted'))

        args1 = (
            request.form.get('number'), request.form.get('stage_bus'), request.form.get('model'), made,
            start, end, deleted,
            request.form.get('about_bus'),
            request.form.get('park'), request.form.get('atp'), photo_id,
            session.get('PROFILE_ID'))

        cur.execute(
            """INSERT INTO FAKEBUSES
        (GOS_NUMBER, STAGE, MODEL, MADE, START, END, DELETED, ABOUT, PARK, ATP_ID, PHOTO_ID, PROFILE_ID, CREATED, MARK)
        VALUES
        (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP(), 0);""", args1)

        args = (session.get('VKID'), request.form.get('number') + request.form.get('model'),
                made + start + end + deleted + request.form.get('park'),
                request.form.get('about_bus'), session.get('IP'))
        cur.execute(
            """INSERT INTO ARCHIVE (VKID, FIELDA, FIELDB, FIELDC, T, IP) VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP(), ?);""",
            args
        )

        con.commit()
        con.close()

        return "okey", 200
    return "unexceptionerror", 500


@app.route('/add_photo_cat_form', methods=['POST', 'GET'])
def add_photo_cat_form():
    if not session.get('RANG') or session.get('RANG') < 7:
        return redirect('/login')

    cur, con = callDB()

    cur.execute(
        """SELECT COUNT(PHOTO_ID) AS A FROM PHOTOS WHERE MODERATED <= 3 AND PUBLISHED = CURRENT_DATE() AND PROFILE_ID = ?;""",
        (session.get('PROFILE_ID'),))
    aa = cur.fetchone()['A']

    con.close()

    if aa >= 3 and session.get('RANG') < 10:
        return "limit photo", 499

    if 'photo' not in request.files:
        return "bad photo", 498
    file = request.files['photo']
    if file.filename == '':
        return "bad photo", 498
    if len(file.filename.split('.')) == 0:
        return "bad photo", 498
    if file.filename.split('.')[-1] != 'png':
        return "bad photo", 498
    if file:
        path = str(random.randint(1000, 9999))

        cur, con = callDB()
        args = (
            path, request.form.get('title'), request.form.get('about'),
            request.form.get('scrined'), request.form.get('stage'), request.form.get('isauthor'),
            request.form.get('isai'), session.get('PROFILE_ID'),)
        cur.execute(
            """INSERT INTO PHOTOS
    (PATH, TITLE, ABOUT, SCRINED, PUBLISHED, MODERATED, STAGE, ISAUTHOR, ISAI, PROFILE_ID)
    VALUES
    (?, ?, ?, ?, CURRENT_DATE(), 3, ?, ?, ?, ?) RETURNING PHOTO_ID;""", args
        )
        photo_id = cur.fetchone()['PHOTO_ID']

        file.save(os.path.join('static/photos', str(photo_id) + path + '.png'))
        # file.save(os.path.join('static/icons', str(photo_id) + path + '.jpg'))

        # try:

        image = Image.open(os.path.join('static/photos', str(photo_id) + path + '.png'))
        rgb_im = image.convert('RGB')
        width, height = rgb_im.size
        rgb_im.thumbnail((500, int(500 * height / width)))
        rgb_im.save(os.path.join('static/icons', str(photo_id) + path + '.jpg'), quality='web_high')
        # except:
        #    return str(traceback.format_exc())

        args = (session.get('VKID'), str(photo_id) + path,
                request.form.get('title') + str(request.form.get('scrined')),
                request.form.get('about'), session.get('IP'))
        cur.execute(
            """INSERT INTO ARCHIVE (VKID, FIELDA, FIELDB, FIELDC, T, IP) VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP(), ?);""",
            args
        )

        args = (photo_id, request.form.get('bus'))
        cur.execute(
            """INSERT INTO PHOTOCATS (PHOTO_ID, CATS_ID) VALUES (?, ?);""",
            args
        )

        con.commit()
        con.close()

        return "okey", 200
    return "unexceptionerror", 500


@app.route('/load_form', methods=['POST'])
def load_form():
    if not session.get('RANG') or session.get('RANG') < 90:
        abort(403)
    if 'table' not in request.files:
        return "Таблица не загрузилась. Попробуйте снова"
    file = request.files['table']
    if file.filename == '':
        return "Таблица не загрузилась. Попробуйте снова"
    if len(file.filename.split('.')) == 0:
        return "Некорректное название. Попробуйте снова"
    if file.filename.split('.')[-1] != 'csv':
        return "Принимаем только .csv (без капса) Попробуйте снова"
    if file:
        try:
            path = str(random.randint(10000, 99999))
            file.save(os.path.join('static/temp', path + '.csv'))

            args = []

            with open(os.path.join('static/temp', path + '.csv'), encoding='utf-8') as table:
                for line in table:
                    stryke = line.strip().split(',')
                    arg = (stryke[1].replace(' ', ''), stryke[2], stryke[3], stryke[4].replace('\"', ''),
                           stryke[5] + "-{:02d}-{:02d}".format(random.randint(1, 12), random.randint(1, 28)),
                           stryke[6], stryke[7], stryke[8], stryke[9], stryke[10], stryke[11])
                    args.append(arg)

            args.pop(0)
            cur, con = callDB()

            cur.executemany(
                """INSERT INTO BUSES (GOS_NUMBER, NUMBER, STAGE, MODEL, MADE, START, END, DELETED, ABOUT, PARK, ATP_ID) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);""",
                args)

            cur.execute(
                """INSERT INTO LOGS (PROFILE_ID, DID, DONE, MARK, NEWA, VKID, IP) VALUES (?, CURRENT_TIMESTAMP(), 'Массово загрузил ПС', 20, ?, ?, ?);""",
                (session.get('PROFILE_ID'), path + '.csv', session.get('VKID'), session.get('IP')))

            # os.remove(os.path.join('static/temp', path + '.csv'))
            con.commit()
            con.close()
        except Exception as ex:
            return str(ex)
        return redirect('/mvps/' + args[0][-1])
    return "Прочая ошибка"


@app.route('/delete_my_photo', methods=['POST'])
def delete_my_photo():
    if not session.get('PROFILE_ID'):
        return redirect('/login')
    cur, con = callDB()
    cur.execute(
        """UPDATE PHOTOS SET MODERATED=1 WHERE MODERATED = 3 AND PHOTO_ID = ? AND PROFILE_ID = ?;""",
        (request.form.get('photo'), session.get('PROFILE_ID'),))
    cur.execute("""SELECT CONCAT(PHOTO_ID,PATH) AS PATH FROM PHOTOS WHERE PHOTO_ID = ? AND MODERATED = 1;""",
                (request.form.get('photo'),))
    path = cur.fetchone()['PATH']

    os.remove(os.path.join('static/photos', str(path) + '.png'))
    os.remove(os.path.join('static/icons', str(path) + '.jpg'))

    con.commit()
    con.close()
    return redirect('/myprofile')


@app.route('/delete_my_bus', methods=['POST'])
def delete_my_bus():
    if not session.get('PROFILE_ID'):
        return redirect('/login')
    cur, con = callDB()
    cur.execute(
        """UPDATE PHOTOS SET MODERATED=1 WHERE MODERATED = 3 AND PHOTO_ID = ? AND PROFILE_ID = ?;""",
        (request.form.get('photo'), session.get('PROFILE_ID'),))
    cur.execute(
        """UPDATE FAKEBUSES SET MARK=1 WHERE MARK = 0 AND FAKEBUS_ID = ? AND PROFILE_ID = ?;""",
        (request.form.get('bus'), session.get('PROFILE_ID'),))
    cur.execute("""SELECT CONCAT(PHOTO_ID,PATH) AS PATH FROM PHOTOS WHERE PHOTO_ID = ? AND MODERATED = 1;""",
                (request.form.get('photo'),))
    path = cur.fetchone()['PATH']

    os.remove(os.path.join('static/photos', str(path) + '.png'))
    os.remove(os.path.join('static/icons', str(path) + '.jpg'))

    con.commit()
    con.close()
    return redirect('/myprofile')


@app.route('/delete_photo_power', methods=['POST'])
def delete_photo_power():
    if not session.get('RANG') or session.get('RANG') < 40:
        abort(403)
    cur, con = callDB()
    cur.execute(
        """UPDATE PHOTOS SET MODERATED=1 WHERE PHOTO_ID = ?;""",
        (request.form.get('photo'),))
    cur.execute("""SELECT CONCAT(PHOTO_ID,PATH) AS PATH FROM PHOTOS WHERE PHOTO_ID = ? AND MODERATED = 1;""",
                (request.form.get('photo'),))
    path = cur.fetchone()['PATH']

    os.remove(os.path.join('static/photos', str(path) + '.png'))
    os.remove(os.path.join('static/icons', str(path) + '.jpg'))

    con.commit()
    con.close()
    return redirect('/photomoderation')



@app.route('/key')
def key():
    if not session.get('RANG') or session.get('RANG') < 90:
        abort(404)
    os.remove('.flask_secret')
    return redirect('/index')

@app.route('/okey_photo', methods=['POST'])
def okey_photo():
    if not session.get('RANG') or session.get('RANG') < 40:
        abort(403)
    cur, con = callDB()

    cur.execute(
        """SELECT PROFILE_ID, MARK, ADM FROM PHOTOS WHERE PHOTO_ID = ?;""",
        (request.form.get('photo'),))
    photo_info = cur.fetchone()
    author, mark, adm = photo_info['PROFILE_ID'], photo_info['MARK'], photo_info['ADM']

    if False and author == session.get('PROFILE_ID'):
        con.close()
        return 'Свои фото оценивать нельзя'
    if int(request.form.get('mark')) < 7:
        cur.execute(
            """UPDATE PHOTOS SET MODERATED=?, COMMENT=?, MARK=3, ADM=5 WHERE PHOTO_ID = ?;""",
            (request.form.get('mark'), request.form.get('comment'), request.form.get('photo'),))
        cur.execute(
            """INSERT INTO LOGS (PROFILE_ID, DID, DONE, MARK, NEWA, NEWB, NEWC, VKID, IP) VALUES (?, CURRENT_TIMESTAMP(), 'Отклонил фото фотографию', 0, ?, ?, ?, ?, ?);""",
            (session.get('PROFILE_ID'),
             request.form.get('mark'), request.form.get('comment'), request.form.get('photo'), session.get('VKID'),
             session.get('IP')))
        con.commit()
        con.close()
        return redirect('/photomoderation')
    if adm == session.get('PROFILE_ID') or adm == 5:
        cur.execute(
            """UPDATE PHOTOS SET MARK=?, COMMENT=?, ADM=? WHERE PHOTO_ID = ?;""",
            (request.form.get('mark'), request.form.get('comment'), session.get('PROFILE_ID'),
             request.form.get('photo'),))
        cur.execute(
            """INSERT INTO LOGS (PROFILE_ID, DID, DONE, MARK, NEWA, NEWB, NEWC, VKID, IP) VALUES (?, CURRENT_TIMESTAMP(), 'Предоценил фото', 0, ?, ?, ?, ?, ?);""",
            (session.get('PROFILE_ID'),
             request.form.get('mark'), request.form.get('comment'), request.form.get('photo'), session.get('VKID'),
             session.get('IP')))
        con.commit()
        con.close()
        return redirect('/photomoderation')
    else:
        cur.execute(
            """UPDATE PHOTOS SET MODERATED=?, COMMENT=? WHERE PHOTO_ID = ?;""",
            (request.form.get('mark'), request.form.get('comment'),
             request.form.get('photo'),))
        cur.execute(
            """INSERT INTO LOGS (PROFILE_ID, DID, DONE, MARK, NEWA, NEWB, NEWC, VKID, IP) VALUES (?, CURRENT_TIMESTAMP(), 'Оценил фото', 0, ?, ?, ?, ?, ?);""",
            (session.get('PROFILE_ID'),
             request.form.get('mark'), request.form.get('comment'), request.form.get('photo'), session.get('VKID'),
             session.get('IP')))
        con.commit()
        con.close()
        return redirect('/photomoderation')
    con.commit()
    con.close()
    return redirect('/photomoderation')


@app.route('/okey_bus', methods=['POST'])
def okey_bus():
    if not session.get('RANG') or session.get('RANG') < 50:
        abort(403)
    cur, con = callDB()

    if int(request.form.get('mark')) >= 7:
        cur.execute(
            """UPDATE PHOTOS SET MARK=?, COMMENT=?, ADM=? WHERE PHOTO_ID = ?;""",
            (request.form.get('mark'), request.form.get('comment'), session.get('PROFILE_ID'),
             request.form.get('photo'),))
        cur.execute(
            """INSERT INTO LOGS (PROFILE_ID, DID, DONE, MARK, NEWA, NEWB, NEWC, VKID, IP) VALUES (?, CURRENT_TIMESTAMP(), 'Оценил автобус', 0, ?, ?, ?, ?, ?);""",
            (session.get('PROFILE_ID'),
             request.form.get('mark'), request.form.get('comment'),
             request.form.get('photo') + ' ' + request.form.get('bus'), session.get('VKID'), session.get('IP')))
        cur.execute(
            """UPDATE FAKEBUSES SET MARK=3 WHERE FAKEBUS_ID = ?;""",
            (request.form.get('bus'),))
        cur.execute(
            """INSERT INTO BUSES (GOS_NUMBER, MODEL, MADE, START, END, DELETED, PARK, ABOUT, ATP_ID, STAGE)
            SELECT GOS_NUMBER, MODEL, MADE, START, END, DELETED, PARK, ABOUT, ATP_ID, STAGE
            FROM FAKEBUSES WHERE FAKEBUS_ID=? RETURNING BUS_ID, START;""",
            (request.form.get('bus'),))
        new_bus = cur.fetchone()
        cur.execute(
            """INSERT INTO EVENTS (DAY, ABOUT, BUS_ID, STAGE) VALUES (?, 'Поступил на предприятие' , ?, 2);""",
            (new_bus['START'], new_bus['BUS_ID']))
        cur.execute(
            """INSERT INTO PHOTOBUS (PHOTO_ID, BUS_ID, ROUTE) VALUES (?, ?, '');""",
            (request.form.get('photo'), new_bus['BUS_ID']))


    else:
        cur.execute(
            """UPDATE PHOTOS SET MODERATED=?, COMMENT=? WHERE PHOTO_ID = ?;""",
            (request.form.get('mark'), request.form.get('comment'), request.form.get('photo'),))
        cur.execute(
            """INSERT INTO LOGS (PROFILE_ID, DID, DONE, MARK, NEWA, NEWB, NEWC, VKID, IP) VALUES (?, CURRENT_TIMESTAMP(), 'Оценил автобус', 0, ?, ?, ?, ?, ?);""",
            (session.get('PROFILE_ID'),
             request.form.get('mark'), request.form.get('comment'),
             request.form.get('photo') + ' ' + request.form.get('bus'), session.get('VKID'), session.get('IP'),
             session.get('VKID'), session.get('IP')))
        cur.execute(
            """UPDATE FAKEBUSES SET MARK=2 WHERE FAKEBUS_ID = ?;""",
            (request.form.get('bus'),))

    con.commit()
    con.close()
    return redirect('/busmoderation')


@app.errorhandler(404)
def not_found_error(error):
    return render_template('404.html'), 404


@app.errorhandler(403)
def not_found_error(error):
    login_link = '/auth'
    return render_template('403.html', link=login_link), 403


@app.errorhandler(500)
def not_found_error(error):
    return render_template('500.html'), 500


@app.errorhandler(502)
def not_found_error(error):
    return render_template('502.html'), 502


@app.errorhandler(405)
def not_found_error(error):
    return render_template('405.html'), 405


if __name__ == "__main__":
    app.run(host='0.0.0.0')
