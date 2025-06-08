# ayat_utils.py
# -*- coding: utf-8 -*-

import time
import json
import sys
import shutil
import sqlite3
import os
import re
import collections
import random
import traceback
import xml.etree.ElementTree as ET
from kivy.utils import platform

SOURCE_DATABASE_NAME = "kuran_uyg_genel_data.db"
DATABASE_FILE = os.path.join(get_app_root_path(), SOURCE_DATABASE_NAME)

MAX_HISTORY_SIZE = 50
MAX_FAVORITE_AYETS_SIZE = 500

hoca_veritabani = {}
site_id_to_hoca_tam_ad_haritasi = {}
sure_konulari_cache = None
query_history = collections.deque(maxlen=MAX_HISTORY_SIZE)
ayet_cache = {}
favorite_ayets_list = collections.deque(maxlen=MAX_FAVORITE_AYETS_SIZE)

def get_app_root_path():
    """Uygulamanın çalıştırıldığı platforma göre kök veya veri dizinini döndürür."""
    if platform == 'android':
        # Android'de uygulamanın özel, yazılabilir veri klasörü
        return App.get_running_app().user_data_dir
    else:
        # Masaüstü (Windows, Linux, macOS) için kodun çalıştığı dizin
        if getattr(sys, 'frozen', False):
            # PyInstaller gibi bir araçla paketlenmişse
            return os.path.dirname(sys.executable)
        return os.path.dirname(os.path.abspath(__file__))

def initialize_database():
    """
    Veritabanının yazılabilir bir konumda olup olmadığını kontrol eder.
    Eğer yoksa, uygulama paketindeki (salt-okunur) veritabanını
    yazılabilir konuma kopyalar.
    """
    app_path = get_app_root_path()
    db_path_in_writable_dir = os.path.join(app_path, SOURCE_DATABASE_NAME)

    # Eğer veritabanı zaten yazılabilir alanda varsa, bir şey yapma
    if os.path.exists(db_path_in_writable_dir):
        cprint_debug(f"Veritabanı zaten mevcut: {db_path_in_writable_dir}", "DB_INIT")
        return

    cprint_debug(f"Veritabanı bulunamadı. Kopyalanacak: {db_path_in_writable_dir}", "DB_INIT")

    # Uygulama paketinin içindeki kaynak veritabanının yolunu bul
    # Bu yol, masaüstünde farklı, Android'de farklı olabilir.
    # Genellikle masaüstünde aynı dizindedir.
    source_db_path_candidates = [
        os.path.join(os.path.dirname(os.path.abspath(__file__)), SOURCE_DATABASE_NAME), # Geliştirme ortamı
        os.path.join(sys._MEIPASS, SOURCE_DATABASE_NAME) if hasattr(sys, '_MEIPASS') else '' # PyInstaller için
    ]
    
    # Android için, Buildozer varlıkları ana dizine koyar
    if platform == 'android':
         # Android'de uygulama paketinin kök dizinini bulmak daha karmaşıktır.
         # Genellikle 'get_asset_path' gibi bir helper fonksiyon kullanılır.
         # Şimdilik, Buildozer'ın dosyayı uygulamanın mevcut çalışma dizinine
         # koyduğunu varsayarak basit bir yaklaşım deneyelim.
         from kivy.app import App
         # Bu, Android'de uygulamanın yüklendiği ana dizini verir (örn: /data/user/0/org.test.kuranapp/files)
         # Ancak paketlenmiş orijinal dosya burada değildir.
         # Orijinal dosya, APK içindedir ve doğrudan erişilemez.
         # Buildozer, source.include_exts ile eklenen dosyaları
         # uygulamanın başlangıç dizinine (cwd) kopyalar.
         source_db_path = os.path.join(os.getcwd(), SOURCE_DATABASE_NAME)
    else:
        source_db_path = source_db_path_candidates[0]


    found_source = False
    if os.path.exists(source_db_path):
        found_source = True
    else: # Diğer adayları dene
        for candidate in source_db_path_candidates:
            if candidate and os.path.exists(candidate):
                source_db_path = candidate
                found_source = True
                break
    
    if not found_source:
        cprint_debug(f"HATA: Kaynak veritabanı '{SOURCE_DATABASE_NAME}' hiçbir konumda bulunamadı!", "DB_INIT_FATAL")
        # Burada uygulamayı durdurmak veya bir hata popup'ı göstermek iyi olabilir.
        return

    try:
        # Yazılabilir klasörün var olduğundan emin ol
        os.makedirs(app_path, exist_ok=True)
        # Kopyalama işlemini yap
        shutil.copy2(source_db_path, db_path_in_writable_dir)
        cprint_debug(f"Veritabanı başarıyla '{source_db_path}' konumundan '{db_path_in_writable_dir}' konumuna kopyalandı.", "DB_INIT_SUCCESS")
    except Exception as e:
        cprint_debug(f"HATA: Veritabanı kopyalanırken hata oluştu: {e}", "DB_INIT_COPY_ERROR")
        traceback.print_exc()

def cprint_debug(text, prefix="DEBUG"):
    print(f"[{prefix}] {time.strftime('%Y-%m-%d %H:%M:%S')} - {text}")

def _normalize_sure_name_for_matching(name_input_str):
    """
    Sure adlarını ve alias'larını veritabanı araması ve karşılaştırması için normalleştirir.
    Küçük harfe çevirir ve belirli Türkçe karakterleri ve kesme işaretlerini basitleştirir.
    """
    if not isinstance(name_input_str, str):
        return ""
    # Önceki SURE_ALIAS_TO_NUMBER_MAP oluşturma mantığındaki normalleştirmeyi temel alır
    return name_input_str.lower().replace("â", "a").replace("î", "i").replace("û", "u").replace("’", "").replace("'", "").strip()

def get_sure_no_from_name_db(sure_adi_girisi):
    """
    Verilen sure adı veya alias'ına göre Surahs tablosundan sure numarasını bulur.

    Args:
        sure_adi_girisi (str): Kullanıcının girdiği sure adı.

    Returns:
        int: Bulunan sure numarası. Eşleşme bulunamazsa None.
    """
    normalized_input = _normalize_sure_name_for_matching(sure_adi_girisi)
    if not normalized_input:
        cprint_debug(f"UYARI: Boş veya geçersiz sure adı girişi: '{sure_adi_girisi}'", "SURE_LOOKUP")
        return None

    conn = None
    try:
        conn = sqlite3.connect(DATABASE_FILE) # Global DATABASE_FILE sabitini kullanır
        cursor = conn.cursor()

        # Tüm surelerin adlarını ve alias'larını çekerek Python içinde karşılaştırma yapacağız
        # Bu, 114 sure için kabul edilebilir bir performanstadır ve normalleştirmeyi kolaylaştırır.
        cursor.execute("SELECT surah_number, name, aliases FROM Surahs")
        all_surahs_data = cursor.fetchall()

        for surah_number, db_name, aliases_json_str in all_surahs_data:
            # 1. Ana sure adını kontrol et
            normalized_db_name = _normalize_sure_name_for_matching(db_name)
            if normalized_db_name == normalized_input:
                return surah_number

            # 2. Alternatif isimleri (aliases) kontrol et
            if aliases_json_str:
                try:
                    aliases_list = json.loads(aliases_json_str) # JSON string'i Python listesine çevir
                    if isinstance(aliases_list, list):
                        for alias in aliases_list:
                            normalized_db_alias = _normalize_sure_name_for_matching(alias)
                            if normalized_db_alias == normalized_input:
                                return surah_number
                except json.JSONDecodeError:
                    cprint_debug(f"UYARI: Sure no {surah_number} ('{db_name}') için 'aliases' JSON verisi ayrıştırılamadı: {aliases_json_str}", "SURE_LOOKUP_JSON_ERR")
                    # Hatalı JSON verisi olan sure için diğer sureleri kontrol etmeye devam et
                    continue
        
        # Eğer döngü tamamlanır ve eşleşme bulunamazsa
        cprint_debug(f"BİLGİ: '{sure_adi_girisi}' (normalize edilmiş: '{normalized_input}') için sure numarası bulunamadı.", "SURE_LOOKUP_NOT_FOUND")
        return None

    except sqlite3.Error as e:
        cprint_debug(f"HATA: get_sure_no_from_name_db veritabanı hatası: {e}", "SURE_LOOKUP_DB_ERR")
        return None
    finally:
        if conn:
            conn.close()

def save_last_read_location(sure_no, ayet_no):
    """Kullanıcının son okuduğu konumu UserSettings tablosuna kaydeder."""
    if not isinstance(sure_no, int) or not isinstance(ayet_no, int):
        cprint_debug(f"HATA: save_last_read_location geçersiz veri aldı: S:{sure_no} A:{ayet_no}", "BOOKMARK_SAVE_ERR")
        return False
    
    location_data = {"sure_no": sure_no, "ayet_no": ayet_no}
    location_json = json.dumps(location_data)
    
    conn = None
    try:
        conn = sqlite3.connect(DATABASE_FILE)
        cursor = conn.cursor()
        cursor.execute("INSERT OR REPLACE INTO UserSettings (setting_key, setting_value) VALUES (?, ?)",
                       ("last_read_location", location_json))
        conn.commit()
        cprint_debug(f"Yer işareti kaydedildi: {location_data}", "BOOKMARK_SAVE_SUCCESS")
        return True
    except sqlite3.Error as e:
        if conn: conn.rollback()
        cprint_debug(f"HATA: Yer işareti kaydedilirken SQLite hatası: {e}", "BOOKMARK_SAVE_SQL_ERR")
        return False
    finally:
        if conn: conn.close()

def load_last_read_location():
    """Kaydedilmiş son okuma konumunu UserSettings tablosundan yükler."""
    conn = None
    try:
        conn = sqlite3.connect(DATABASE_FILE)
        cursor = conn.cursor()
        cursor.execute("SELECT setting_value FROM UserSettings WHERE setting_key = ?", ("last_read_location",))
        row = cursor.fetchone()
        
        if row and row[0]:
            location_data = json.loads(row[0])
            sure_no = location_data.get('sure_no')
            ayet_no = location_data.get('ayet_no')
            if isinstance(sure_no, int) and isinstance(ayet_no, int):
                cprint_debug(f"Yer işareti yüklendi: {location_data}", "BOOKMARK_LOAD_SUCCESS")
                return sure_no, ayet_no
        
        cprint_debug("Kaydedilmiş yer işareti bulunamadı.", "BOOKMARK_NOT_FOUND")
        return None, None
    except (sqlite3.Error, json.JSONDecodeError, TypeError) as e:
        cprint_debug(f"HATA: Yer işareti yüklenirken hata: {e}", "BOOKMARK_LOAD_ERR")
        return None, None
    finally:
        if conn: conn.close()	

def get_sure_details_db(surah_number_input):
    """
    Verilen sure numarasına göre Surahs tablosundan sure detaylarını (ad, ayet sayısı) alır.

    Args:
        surah_number_input (int): Sure numarası.

    Returns:
        dict: {'name': str, 'ayah_count': int} formatında sure detayları.
              Eğer sure bulunamazsa veya giriş geçersizse None.
    """
    if not isinstance(surah_number_input, int) or not (1 <= surah_number_input <= 114):
        cprint_debug(f"UYARI: Geçersiz sure numarası girişi: {surah_number_input}. (1-114 arasında olmalıdır)", "SURE_DETAILS_PARAM_ERR")
        return None

    conn = None
    try:
        conn = sqlite3.connect(DATABASE_FILE) # Global DATABASE_FILE sabitini kullanır
        cursor = conn.cursor()

        cursor.execute("SELECT name, ayah_count FROM Surahs WHERE surah_number = ?", (surah_number_input,))
        row = cursor.fetchone()

        if row:
            # row[0] -> name, row[1] -> ayah_count
            return {'name': str(row[0]), 'ayah_count': int(row[1])}
        else:
            cprint_debug(f"BİLGİ: {surah_number_input} numaralı sure için veritabanında detay bulunamadı.", "SURE_DETAILS_NOT_FOUND")
            return None

    except sqlite3.Error as e:
        cprint_debug(f"HATA: get_sure_details_db fonksiyonunda veritabanı hatası: {e}", "SURE_DETAILS_DB_ERR")
        return None
    finally:
        if conn:
            conn.close()

def parse_sure_ayet_input(input_str):
    input_str = str(input_str).strip() # Girdiyi string'e çevir ve temizle
    parts = input_str.split()

    if not parts:
        return None, [], False # Boş giriş için

    # Değişkenleri başlangıçta tanımlayalım
    sure_no_found = None
    ayet_no_list_parsed = []
    is_range_parsed = False
    current_sure_name_for_debug = ""

    # Ayet aralığı kontrolü (örn: "Bakara 5-7" veya "2 5-7")
    # Son kısım '-' içeriyorsa ve en az iki kısım varsa (sure + aralık)
    if len(parts) >= 2 and '-' in parts[-1]:
        try:
            range_part = parts[-1]
            start_ayet_str, end_ayet_str = range_part.split('-', 1)
            start_ayet = int(re.sub(r'[^\d]', '', start_ayet_str)) # Sadece rakamları al
            end_ayet = int(re.sub(r'[^\d]', '', end_ayet_str))   # Sadece rakamları al

            if not (0 < start_ayet <= end_ayet): # start_ayet > 0 olmalı ve start_ayet <= end_ayet olmalı
                raise ValueError("Ayet aralığı geçersiz (başlangıç > bitiş veya negatif).")

            sure_name_candidate_parts = parts[:-1]
            if not sure_name_candidate_parts: # Sadece "-5" gibi bir giriş varsa (örn: " -5-7" )
                raise ValueError("Sure adı veya numarası eksik.")
            
            sure_name_candidate = " ".join(sure_name_candidate_parts).strip()

            # Sure numarasını bulma
            if sure_name_candidate.isdigit():
                potential_sure_no = int(sure_name_candidate)
                temp_details = get_sure_details_db(potential_sure_no)
                if temp_details:
                    sure_no_found = potential_sure_no
                    current_sure_name_for_debug = temp_details['name']
            
            if not sure_no_found: # Sayısal değilse veya sayısal olup da geçerli sure değilse, isim olarak ara
                sure_no_found = get_sure_no_from_name_db(sure_name_candidate)
                if sure_no_found:
                    temp_details = get_sure_details_db(sure_no_found) # İsmi almak için tekrar çağır
                    if temp_details:
                        current_sure_name_for_debug = temp_details['name']
                    else: # Bu durum get_sure_no_from_name_db sonrası pek olası değil ama garanti olsun
                         raise ValueError(f"'{sure_name_candidate}' için sure detayı alınamadı (no: {sure_no_found}).")


            if not sure_no_found:
                raise ValueError(f"Sure adı veya numarası bulunamadı: '{sure_name_candidate}'")

            # Ayet sayısını al ve kontrol et
            sure_details = get_sure_details_db(sure_no_found) # Zaten yukarıda alınmış olabilir, tekrar almak yerine optimize edilebilir.
                                                            # Ama get_sure_details_db cache'lemediği için sorun yok.
            if not sure_details:
                # Bu durum, sure_no_found geçerli bir numara ise pek olası değil.
                cprint_debug(f"HATA: '{sure_name_candidate}' (no: {sure_no_found}) için sure detayları veritabanından alınamadı.", "PARSE_INPUT_RANGE")
                return None, [], False
            
            max_ayet = sure_details['ayah_count']
            current_sure_name_for_debug = sure_details['name'] # Güncel ismi alalım

            if not (1 <= start_ayet <= max_ayet and 1 <= end_ayet <= max_ayet):
                cprint_debug(f"UYARI: Girdi ({input_str}) için '{current_sure_name_for_debug}' Suresi'nde geçersiz ayet aralığı (1-{max_ayet}). İstenen: {start_ayet}-{end_ayet}", "PARSE_INPUT_RANGE_VALID")
                return None, [], False
            
            ayet_no_list_parsed = list(range(start_ayet, end_ayet + 1))
            is_range_parsed = True
            return sure_no_found, ayet_no_list_parsed, is_range_parsed
        
        except ValueError as e:
            cprint_debug(f"UYARI: Aralık ayrıştırma hatası: Giriş='{input_str}', Hata='{e}'", "PARSE_INPUT_RANGE_EXC")
            return None, [], False # Aralık hatalıysa, tek ayet olarak denenmesini engellemek için burada None döndür

    # Tek ayet veya sure adı + tek ayet durumu (örn: "Bakara 5", "2 5", veya sadece sure adı "Fatiha")
    # Not: Sadece sure adı girilirse (örn: "Fatiha"), bu fonksiyon ayet no döndürmemeli,
    # bu durum daha üst seviyede ele alınabilir veya fonksiyonun amacı sadece tam s:a girdisi ise bu kısım ona göre ayarlanır.
    # Mevcut mantık ayet numarası bekliyor gibi duruyor.
    if len(parts) >= 1:
        try:
            potential_ayet_no_str = parts[-1]
            # Ayet numarasından sadece rakamları al
            ayet_no_cleaned_str = re.sub(r'[^\d]', '', potential_ayet_no_str) 
            
            ayet_no = -1
            if ayet_no_cleaned_str: # Eğer sayısal bir şey varsa
                ayet_no = int(ayet_no_cleaned_str)
                if ayet_no <= 0: 
                    raise ValueError("Ayet numarası pozitif olmalı.")
            # Eğer ayet_no_cleaned_str boşsa (örn: "Fatiha x"), bu ValueError'a yol açacak veya ayet_no -1 kalacak.

            if len(parts) >= 2: # Sure adı/no + Ayet no (örn: "Bakara 5")
                if ayet_no == -1: # Son kısım ayet numarası olarak ayrıştırılamadıysa ("Fatiha x" gibi)
                    raise ValueError("Son kısım geçerli bir ayet numarası değil.")

                sure_name_candidate = " ".join(parts[:-1]).strip()
                
                if sure_name_candidate.isdigit():
                    potential_sure_no = int(sure_name_candidate)
                    temp_details = get_sure_details_db(potential_sure_no)
                    if temp_details:
                        sure_no_found = potential_sure_no
                
                if not sure_no_found:
                    sure_no_found = get_sure_no_from_name_db(sure_name_candidate)

                if not sure_no_found:
                     raise ValueError(f"Sure adı veya numarası ('{sure_name_candidate}') bulunamadı.")

            elif len(parts) == 1: # Sadece bir parça var. Bu ya "5" (sure eksik) ya da "Fatiha" (ayet eksik)
                                  # ya da "Fatiha:5" (bu regex ile ayıklanmıyor, split ile ayrılıyor)
                                  # Bu fonksiyonun amacı belirli bir sure ve ayeti çözmek olduğu için,
                                  # sadece ayet no veya sadece sure adı girdisi burada None döndürmeli.
                if ayet_no_cleaned_str and not re.search(r'[a-zA-Z]', input_str): # Sadece sayı girilmişse (örn: "5")
                    cprint_debug(f"UYARI: Sadece ayet numarası ('{input_str}') girildi, sure belirtilmedi.", "PARSE_INPUT_SINGLE")
                    return None, [], False 
                else: # Sadece sure adı girilmiş gibi ("Fatiha") veya anlamsız tek kelime
                    cprint_debug(f"UYARI: Girdi ('{input_str}') anlaşılamadı. Format: '[Sure Adı/No] [AyetNo]' veya tam sure adı.", "PARSE_INPUT_SINGLE")
                    return None, [], False

            # sure_no_found ve ayet_no (pozitifse) elimizde
            if sure_no_found and ayet_no > 0:
                sure_details = get_sure_details_db(sure_no_found)
                if not sure_details:
                    cprint_debug(f"HATA: {sure_no_found} için sure detayları alınamadı (tek ayet durumu).", "PARSE_INPUT_SINGLE")
                    return None, [], False # Sure no geçerli değilse (veritabanında yoksa)
                
                max_ayet = sure_details['ayah_count']
                current_sure_name_for_debug = sure_details['name']

                if 1 <= ayet_no <= max_ayet:
                    ayet_no_list_parsed = [ayet_no]
                    is_range_parsed = False
                    return sure_no_found, ayet_no_list_parsed, is_range_parsed
                else:
                    cprint_debug(f"UYARI: {current_sure_name_for_debug} Suresi için ayet no ({ayet_no}) (1-{max_ayet}) aralığında olmalıdır.", "PARSE_INPUT_SINGLE_VALID")
                    return None, [], False
            elif sure_no_found and ayet_no == -1 and len(parts) >= 2: # "Sure Adı X" gibi bir durumdu ve X ayrıştırılamadı
                 cprint_debug(f"UYARI: Girdi ({input_str}) için ayet numarası anlaşılamadı.", "PARSE_INPUT_SINGLE")
                 return None, [], False

        except ValueError as e:
            cprint_debug(f"UYARI: Tek ayet ayrıştırma hatası: Giriş='{input_str}', Hata='{e}'", "PARSE_INPUT_SINGLE_EXC")
            # Hata durumunda aşağıdaki genel None dönüşüne düşecek
            pass 

    # Eğer yukarıdaki bloklardan hiçbiri başarılı bir dönüş yapmadıysa
    cprint_debug(f"UYARI: Girdi ('{input_str}') anlaşılamadı. Format: '[Sure Adı/No] [AyetNo]' veya '[Sure Adı/No] [Baş.Ayet]-[Bitiş.Ayet]'.", "PARSE_INPUT_FAIL")
    return None, [], False

def normalize_turkish_text_for_search(text):
    if not text:
        return ""
    text = text.lower() # Standart küçük harfe çevirme
    # Türkçe'ye özgü karakter dönüşümleri
    replacements = {
        'i̇': 'i',  # Bazen farklı kodlanan noktalı küçük i
        'ı': 'i',
        'ö': 'o',
        'ü': 'u',
        'ş': 's',
        'ç': 'c',
        'ğ': 'g',
        # 'İ': 'i', # .lower() bunu zaten yapar
        # 'I': 'i', # .lower() "ı" yapar, bu yüzden yukarıda 'ı':'i' var
    }
    for char_from, char_to in replacements.items():
        text = text.replace(char_from, char_to)
    return text

def get_sure_name_db(sure_no):
    """
    Verilen sure numarasına göre Surahs tablosundan sure adını alır.

    Args:
        sure_no (int): Sure numarası.

    Returns:
        str: Sure adı. Bulunamazsa None.
    """
    details = get_sure_details_db(sure_no)
    if details:
        return details.get('name')
    return None

def get_ayah_count_db(sure_no):
    """
    Verilen sure numarasına göre Surahs tablosundan ayet sayısını alır.

    Args:
        sure_no (int): Sure numarası.

    Returns:
        int: Ayet sayısı. Bulunamazsa 0 veya None (burada 0 tercih edilebilir).
    """
    details = get_sure_details_db(sure_no)
    if details:
        return details.get('ayah_count', 0)
    return 0

def get_all_surahs_with_aliases_db():
    """
    Surahs tablosundan tüm surelerin numaralarını, ana adlarını ve 
    JSON formatındaki alternatif adlarını (aliases) çekip işler.

    Returns:
        list: Her bir sure için {'number': int, 'name': str, 'aliases': list_of_str}
              formatında sözlükler içeren bir liste. Hata durumunda boş liste.
    """
    conn = None
    surahs_list = []
    try:
        conn = sqlite3.connect(DATABASE_FILE)
        cursor = conn.cursor()
        cursor.execute("SELECT surah_number, name, aliases FROM Surahs ORDER BY surah_number ASC")
        rows = cursor.fetchall()

        for row in rows:
            surah_number, name, aliases_json_str = row
            parsed_aliases = []
            if aliases_json_str:
                try:
                    loaded_aliases = json.loads(aliases_json_str)
                    if isinstance(loaded_aliases, list):
                        # Alias'ların string olduğundan emin olalım
                        parsed_aliases = [str(alias) for alias in loaded_aliases if isinstance(alias, (str, int))]
                    else:
                        cprint_debug(f"UYARI: Sure no {surah_number} ('{name}') için 'aliases' JSON list değil: {type(loaded_aliases)}", "SURAHS_ALIASES_FORMAT")
                except json.JSONDecodeError:
                    cprint_debug(f"UYARI: Sure no {surah_number} ('{name}') için 'aliases' JSON verisi ayrıştırılamadı: {aliases_json_str}", "SURAHS_ALIASES_JSON_ERR")
            
            surahs_list.append({
                'number': int(surah_number),
                'name': str(name),
                'aliases': parsed_aliases
            })
        
        cprint_debug(f"{len(surahs_list)} sure için isim ve alias bilgileri veritabanından yüklendi.", "SURAHS_ALIASES_LOADED")
        return surahs_list

    except sqlite3.Error as e:
        cprint_debug(f"HATA: get_all_surahs_with_aliases_db veritabanı hatası: {e}", "SURAHS_ALIASES_DB_ERR")
        return []
    except Exception as e_gen:
        cprint_debug(f"HATA: get_all_surahs_with_aliases_db genel hata: {e_gen}", "SURAHS_ALIASES_GEN_ERR")
        traceback.print_exc()
        return []
    finally:
        if conn:
            conn.close()

def load_subjects_from_db():
    global sure_konulari_cache
    if sure_konulari_cache is not None:
        cprint_debug("Sure konuları önbellekten yüklendi.", "SUBJECTS_CACHE")
        return sure_konulari_cache

    processed_subjects = {"sure_adlari_sirali": [], "konular_by_sure": {}}
    conn = None
    try:
        conn = sqlite3.connect(DATABASE_FILE) # Global DATABASE_FILE sabitini kullanır
        cursor = conn.cursor()

        # SureKonulari tablosunu Surahs tablosu ile birleştirerek gerekli bilgileri çekiyoruz.
        # surah_number'a göre sıralama, sure_adlari_sirali listesinin doğru sırada olmasını sağlar.
        query = """
            SELECT
                s.name AS sure_adi_display,         -- Surahs tablosundan sure adı
                s.surah_number AS sure_no,          -- Surahs tablosundan sure numarası
                s.ayah_count AS total_ayahs_in_surah, -- Validasyon için suredeki toplam ayet sayısı
                sk.konu_aciklamasi,                 -- SureKonulari tablosundan konu açıklaması
                sk.baslangic_ayet_numarasi          -- SureKonulari tablosundan konunun başladığı ayet
            FROM
                SureKonulari sk
            JOIN
                Surahs s ON sk.surah_db_id = s.surah_db_id
            ORDER BY
                s.surah_number ASC, sk.baslangic_ayet_numarasi ASC; 
        """
        cursor.execute(query)
        rows = cursor.fetchall()

        if not rows:
            cprint_debug("BİLGİ: Veritabanında (SureKonulari/Surahs) işlenecek sure konusu bulunamadı.", "SUBJECTS_DB_EMPTY")
            sure_konulari_cache = processed_subjects # Boş yapıyı cache'le
            return sure_konulari_cache

        for row_data in rows:
            sure_adi_veritabani, sure_no_veritabani, toplam_ayet_surede, konu_metni, baslangic_ayet_veritabani = row_data
            
            # Gelen baslangic_ayet_numarasi değerini integer'a çevir ve doğrula
            try:
                baslangic_ayet_int = int(baslangic_ayet_veritabani)
                # Ayet numarasının geçerli olup olmadığını (1 <= ayet_no <= toplam_ayet) kontrol et
                if not (1 <= baslangic_ayet_int <= toplam_ayet_surede):
                    cprint_debug(f"UYARI: '{sure_adi_veritabani}' Suresi (No: {sure_no_veritabani}), konu '{konu_metni[:30]}...' için geçersiz başlangıç ayeti ({baslangic_ayet_int}). Suredeki toplam ayet sayısı: {toplam_ayet_surede}", "SUBJECTS_AYAH_INVALID_DB")
                    continue # Bu konuyu atla, sonraki konuya geç
            except ValueError:
                cprint_debug(f"UYARI: '{sure_adi_veritabani}' Suresi (No: {sure_no_veritabani}), konu '{konu_metni[:30]}...' için başlangıç ayeti ({baslangic_ayet_veritabani}) sayıya çevrilemedi.", "SUBJECTS_AYAH_FORMAT_DB")
                continue # Bu konuyu atla

            # main.py'nin beklediği konu sözlüğü formatı
            konu_dict = {
                "konu": konu_metni,
                "baslangic_ayet": baslangic_ayet_int,
                "sure_no": sure_no_veritabani,
                "sure_adi_display": sure_adi_veritabani 
            }

            # Eğer bu sure adı processed_subjects içinde ilk kez görülüyorsa,
            # 'sure_adlari_sirali' listesine ekle ve 'konular_by_sure' için yeni bir liste başlat.
            if sure_adi_veritabani not in processed_subjects["konular_by_sure"]:
                processed_subjects["sure_adlari_sirali"].append(sure_adi_veritabani)
                processed_subjects["konular_by_sure"][sure_adi_veritabani] = []
            
            processed_subjects["konular_by_sure"][sure_adi_veritabani].append(konu_dict)

        sure_konulari_cache = processed_subjects # Başarıyla yüklenen veriyi cache'le
        cprint_debug(f"Sure konuları veritabanından yüklendi ve işlendi: {len(processed_subjects['sure_adlari_sirali'])} sure için konular bulundu.", "SUBJECTS_DB_LOADED_SUCCESS")
        return sure_konulari_cache

    except sqlite3.Error as e:
        cprint_debug(f"HATA: Sure konuları veritabanından yüklenirken SQLite hatası oluştu: {e}", "SUBJECTS_DB_SQLITE_ERR")
        sure_konulari_cache = None # Hata durumunda cache'i temizle veya sıfırla
        return {"sure_adlari_sirali": [], "konular_by_sure": {}} # Uygulamanın çökmemesi için boş yapı dön
    except Exception as e:
        cprint_debug(f"HATA: Sure konuları yüklenirken genel bir hata oluştu: {e}", "SUBJECTS_DB_GENERAL_ERR")
        traceback.print_exc() # Hatanın detayını konsola yazdır
        sure_konulari_cache = None
        return {"sure_adlari_sirali": [], "konular_by_sure": {}}
    finally:
        if conn:
            conn.close()

def hoca_veritabani_yukle():
    global hoca_veritabani, site_id_to_hoca_tam_ad_haritasi

    # Önce mevcut verileri temizleyelim
    hoca_veritabani.clear()
    site_id_to_hoca_tam_ad_haritasi.clear()

    conn = None
    try:
        conn = sqlite3.connect(DATABASE_FILE) # Global DATABASE_FILE sabitini kullanır
        cursor = conn.cursor()

        cursor.execute("SELECT hoca_adi, site_idler_json, ozgecmis_calismalar, gorusler_yaklasimlar FROM HocaBilgileri")
        rows = cursor.fetchall()

        if not rows:
            cprint_debug("BİLGİ: HocaBilgileri tablosunda yüklenecek veri bulunamadı.", "HOCA_DB_EMPTY")
            # hoca_veritabani ve site_id_to_hoca_tam_ad_haritasi zaten boş
            return True # Başarıyla boş bir veri seti yüklendi (veya zaten boştu)

        for row_data in rows:
            hoca_adi_db, site_idler_json_str, ozgecmis_db, gorusler_db = row_data
            
            site_idler_list_parsed = []
            if site_idler_json_str:
                try:
                    loaded_list = json.loads(site_idler_json_str)
                    # Gelen verinin gerçekten bir liste olduğundan emin olalım
                    if isinstance(loaded_list, list):
                        site_idler_list_parsed = loaded_list
                    else:
                        cprint_debug(f"UYARI: '{hoca_adi_db}' için 'site_idler_json' DB'den liste olarak gelmedi: {type(loaded_list)}", "HOCA_DB_JSON_FORMAT")
                except json.JSONDecodeError:
                    cprint_debug(f"UYARI: '{hoca_adi_db}' için 'site_idler_json' verisi ayrıştırılamadı: {site_idler_json_str}", "HOCA_DB_JSON_DECODE_ERR")

            # hoca_veritabani global sözlüğünü doldur
            # Yapı, eski JSON dosyasındaki yapı ile aynı olacak şekilde ayarlanır.
            hoca_veritabani[hoca_adi_db] = {
                "site_idler": site_idler_list_parsed,
                "ozgecmis_calismalar": ozgecmis_db if ozgecmis_db is not None else "",
                "gorusler_yaklasimlar": gorusler_db if gorusler_db is not None else ""
            }

            # site_id_to_hoca_tam_ad_haritasi global sözlüğünü doldur
            for site_id in site_idler_list_parsed:
                if isinstance(site_id, str): # site_id'nin string olduğundan emin ol
                    site_id_to_hoca_tam_ad_haritasi[site_id.casefold()] = hoca_adi_db
                else:
                    cprint_debug(f"UYARI: '{hoca_adi_db}' hocası için site ID listesinde string olmayan bir değer bulundu: {site_id}", "HOCA_DB_SITE_ID_TYPE_ERR")
        
        cprint_debug(f"Hoca bilgileri veritabanındaki 'HocaBilgileri' tablosundan yüklendi: {len(hoca_veritabani)} hoca.", "HOCA_DB_LOADED_FROM_DB")
        return True

    except sqlite3.Error as e:
        cprint_debug(f"HATA: Hoca bilgileri 'HocaBilgileri' tablosundan yüklenirken SQLite hatası: {e}", "HOCA_DB_SQLITE_ERR")
        hoca_veritabani.clear() # Hata durumunda global sözlükleri boşalt
        site_id_to_hoca_tam_ad_haritasi.clear()
        return False
    except Exception as e: # Beklenmedik diğer hatalar
        cprint_debug(f"HATA: Hoca bilgileri yüklenirken genel bir hata oluştu: {e}", "HOCA_DB_GENERAL_ERR")
        traceback.print_exc() # Genel hatalar için traceback'i yazdır
        hoca_veritabani.clear()
        site_id_to_hoca_tam_ad_haritasi.clear()
        return False
    finally:
        if conn:
            conn.close()

def get_hoca_bilgisi_data(hoca_tam_adi):
    global hoca_veritabani
    if not hoca_veritabani:
        cprint_debug("Hoca veritabanı boş.", "HOCA_INFO")
        return None
    hoca_verisi = hoca_veritabani.get(hoca_tam_adi)
    if hoca_verisi:
        ozgecmis = hoca_verisi.get('ozgecmis_calismalar', '')
        gorusler = hoca_verisi.get('gorusler_yaklasimlar', '')
        bilgi = (f"Özgeçmiş ve Çalışmaları:\n{ozgecmis}\n\n" if ozgecmis else "") + \
                (f"Görüşler ve Yaklaşımlar:\n{gorusler}" if gorusler else "")
        return {"tam_ad": hoca_tam_adi, "bilgi": bilgi.strip() or "Bu hoca için detaylı bilgi bulunamadı."}
    cprint_debug(f"'{hoca_tam_adi}' için hoca bilgisi bulunamadı.", "HOCA_INFO")
    return None

def clear_query_history_db():
    """
    SorguGecmisi tablosundaki tüm kayıtları siler ve
    global query_history deque'sini temizler.

    Returns:
        bool: İşlem başarılıysa True, aksi halde False.
    """
    global query_history
    conn = None
    try:
        conn = sqlite3.connect(DATABASE_FILE)
        cursor = conn.cursor()

        # SorguGecmisi tablosundaki tüm kayıtları sil
        cursor.execute("DELETE FROM SorguGecmisi")
        conn.commit()
        
        # Global query_history deque'sini de temizle
        query_history.clear()
        
        cprint_debug("Sorgu geçmişi (veritabanı 'SorguGecmisi' tablosu ve uygulama içi 'query_history' deque) başarıyla temizlendi.", "HISTORY_CLEAR_DB_SUCCESS")
        return True

    except sqlite3.Error as e:
        if conn:
            conn.rollback() # Hata durumunda işlemleri geri al
        cprint_debug(f"HATA: Sorgu geçmişi veritabanından ('SorguGecmisi' tablosu) silinirken SQLite hatası: {e}", "HISTORY_CLEAR_DB_SQLITE_ERR")
        return False
    except Exception as e:
        if conn:
            conn.rollback() # Genel hatalarda da geri almayı dene
        cprint_debug(f"HATA: Sorgu geçmişi temizlenirken genel bir hata oluştu: {e}", "HISTORY_CLEAR_DB_GENERAL_ERR")
        traceback.print_exc()
        return False
    finally:
        if conn:
            conn.close()

def clear_ayet_cache_file(): # Fonksiyon adını daha sonra clear_app_runtime_data gibi değiştirebiliriz.
    global ayet_cache
    cache_temizlendi_mi = False
    history_temizlendi_mi = False

    try:
        ayet_cache.clear() # Dosya işlemleri yerine global sözlüğü temizle
        cprint_debug("Ayet önbelleği (in-memory: ayet_cache) başarıyla temizlendi.", "CACHE_CLEAR")
        cache_temizlendi_mi = True
    except Exception as e:
        cprint_debug(f"HATA: Ayet önbelleği (in-memory: ayet_cache) temizlenirken bir hata oluştu: {e}", "CACHE_CLEAR_ERROR")

    # Sorgu geçmişini temizle
    history_temizlendi_mi = clear_query_history_db() # Bu fonksiyon zaten kendi loglarını basıyor

    if cache_temizlendi_mi and history_temizlendi_mi:
        return "all_success"  # Hem önbellek hem geçmiş başarıyla temizlendi
    elif cache_temizlendi_mi:
        return "cache_only_success"  # Sadece önbellek temizlendi, geçmişte sorun oldu
    elif history_temizlendi_mi:
        return "history_only_success"  # Sadece geçmiş temizlendi, önbellekte sorun oldu
    else:
        return "all_fail"

def load_query_history():
    global query_history
    conn = None
    try:
        conn = sqlite3.connect(DATABASE_FILE)
        cursor = conn.cursor()

        query = """
            SELECT
                QG.sorgu_db_id,             -- << YENİ: Geçmiş Kaydının Benzersiz ID'si
                A.surah_number,
                A.ayah_number_in_surah,
                S.name AS surah_name,
                A.arabic_text               -- Bu hala alınıyor ama HistoryScreen'de gösterilmeyecek
            FROM
                SorguGecmisi QG
            JOIN
                Ayahs A ON QG.ayah_db_id = A.ayah_db_id
            JOIN
                Surahs S ON A.surah_number = S.surah_number
            ORDER BY
                QG.sorgu_zamani DESC
            LIMIT ?;
        """
        cursor.execute(query, (MAX_HISTORY_SIZE,))
        rows = cursor.fetchall()

        loaded_history_items = []
        for row in rows:
            # Yeni tuple formatı: (sorgu_db_id, sure_no, ayet_no, sure_adi, arapca_metin)
            try:
                loaded_history_items.append(
                    (int(row[0]), int(row[1]), int(row[2]), str(row[3]), str(row[4]))
                )
            except (ValueError, TypeError, IndexError) as e:
                cprint_debug(f"UYARI: Geçmiş yüklenirken hatalı satır formatı: {row}. Hata: {e}", "HISTORY_LOAD_DB_ROW_ERR")

        query_history = collections.deque(loaded_history_items, maxlen=MAX_HISTORY_SIZE)
        cprint_debug(f"Sorgu geçmişi veritabanından başarıyla yüklendi ({len(query_history)} kayıt).", "HISTORY_LOAD_DB_SUCCESS")

    except sqlite3.Error as e:
        cprint_debug(f"HATA: Sorgu geçmişi veritabanından yüklenirken SQLite hatası: {e}", "HISTORY_LOAD_DB_SQLITE_ERR")
        query_history = collections.deque(maxlen=MAX_HISTORY_SIZE)
    except Exception as e:
        cprint_debug(f"HATA: Sorgu geçmişi yüklenirken genel bir hata oluştu: {e}", "HISTORY_LOAD_DB_GENERAL_ERR")
        traceback.print_exc()
        query_history = collections.deque(maxlen=MAX_HISTORY_SIZE)
    finally:
        if conn:
            conn.close()

def delete_single_history_entry_db(sorgu_id_to_delete):
    """
    Verilen sorgu_db_id'ye sahip tek bir geçmiş kaydını SorguGecmisi tablosundan siler.
    Başarılı silme işleminden sonra global query_history listesini yeniler.
    """
    global query_history # Global query_history'yi yenilemek için
    if not isinstance(sorgu_id_to_delete, int):
        cprint_debug(f"HATA: delete_single_history_entry_db - Geçersiz sorgu_id tipi: {type(sorgu_id_to_delete)}", "HISTORY_DEL_SORGUID_TYPE_ERR")
        return False

    conn = None
    try:
        conn = sqlite3.connect(DATABASE_FILE)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM SorguGecmisi WHERE sorgu_db_id = ?", (sorgu_id_to_delete,))
        conn.commit()

        deleted_rows = cursor.rowcount
        if deleted_rows > 0:
            cprint_debug(f"Geçmiş kaydı (sorgu_db_id: {sorgu_id_to_delete}) başarıyla silindi.", "HISTORY_DEL_SORGUID_SUCCESS")
            load_query_history() # Deque'yi veritabanından güncel durumla yeniden yükle
            return True
        else:
            cprint_debug(f"Silinecek geçmiş kaydı bulunamadı (sorgu_db_id: {sorgu_id_to_delete}).", "HISTORY_DEL_SORGUID_NOT_FOUND")
            # Kayıt bulunamasa bile, olası tutarsızlıklara karşı deque'yi yine de yenileyebiliriz.
            load_query_history()
            return False # Veya True dönebilir, "bulunamadı" bir hata sayılmazsa. Şimdilik False.

    except sqlite3.Error as e:
        if conn:
            conn.rollback()
        cprint_debug(f"HATA: Geçmişten belirli kayıt (sorgu_db_id: {sorgu_id_to_delete}) silinirken (SQLite): {e}", "HISTORY_DEL_SORGUID_SQLITE_ERR")
        return False
    except Exception as e_gen: # Genel hatalar için
        if conn:
            conn.rollback()
        cprint_debug(f"HATA: Geçmiş kaydı silinirken genel bir hata oluştu (sorgu_db_id: {sorgu_id_to_delete}): {e_gen}", "HISTORY_DEL_SORGUID_GENERAL_ERR")
        traceback.print_exc()
        return False
    finally:
        if conn:
            conn.close()

def add_query_to_history_db(ayah_db_id_param):
    """
    Verilen bir ayet ID'sini (Ayahs.ayah_db_id) SorguGecmisi tablosuna ekler.
    Eğer geçmişteki toplam kayıt sayısı MAX_HISTORY_SIZE'ı aşarsa,
    en eski kayıtları otomatik olarak siler.

    Args:
        ayah_db_id_param (int): Sorgulanan ayetin veritabanındaki ayah_db_id'si.

    Returns:
        bool: İşlem (ekleme ve potansiyel silme) başarılıysa True, aksi halde False.
    """
    if not isinstance(ayah_db_id_param, int):
        cprint_debug(f"HATA: add_query_to_history_db - Geçersiz ayah_db_id_param tipi: {type(ayah_db_id_param)}", "HISTORY_ADD_DB_TYPE_ERR")
        return False

    conn = None
    try:
        conn = sqlite3.connect(DATABASE_FILE)
        cursor = conn.cursor()

        # 1. Yeni sorguyu (ayet ID'sini) SorguGecmisi tablosuna ekle.
        # 'sorgu_zamani' sütunu tabloda DEFAULT CURRENT_TIMESTAMP olarak tanımlı olduğu için ayrıca belirtmeye gerek yok.
        cursor.execute("INSERT INTO SorguGecmisi (ayah_db_id) VALUES (?)", (ayah_db_id_param,))
        
        # 2. Geçmişteki toplam kayıt sayısını kontrol et.
        cursor.execute("SELECT COUNT(*) FROM SorguGecmisi")
        current_history_count = cursor.fetchone()[0]

        # 3. Eğer kayıt sayısı MAX_HISTORY_SIZE'ı aşıyorsa, en eski kayıtları sil.
        if current_history_count > MAX_HISTORY_SIZE:
            num_to_delete = current_history_count - MAX_HISTORY_SIZE
            # En eski kayıtları (sorgu_zamani'na göre artan sırada) bularak sil.
            # LIMIT ile silinecek kayıt sayısını belirt.
            cursor.execute("""
                DELETE FROM SorguGecmisi
                WHERE sorgu_db_id IN (
                    SELECT sorgu_db_id FROM SorguGecmisi
                    ORDER BY sorgu_zamani ASC
                    LIMIT ?
                )
            """, (num_to_delete,))
            cprint_debug(f"Sorgu geçmişinden en eski {num_to_delete} kayıt (limit: {MAX_HISTORY_SIZE}) veritabanından silindi.", "HISTORY_TRIM_DB")

        conn.commit()
        # UI'daki 'query_history' deque'sinin güncellenmesi için main.py veya Kivy App tarafında
        # bu işlemden sonra load_query_history() fonksiyonunun tekrar çağrılması gerekecektir.
        return True

    except sqlite3.Error as e:
        if conn:
            conn.rollback() # Hata durumunda işlemleri geri al
        cprint_debug(f"HATA: Sorgu geçmişine kayıt eklenirken veya eski kayıtlar silinirken (SQLite): {e}", "HISTORY_ADD_DB_SQLITE_ERR")
        return False
    except Exception as e:
        if conn:
            conn.rollback()
        cprint_debug(f"HATA: Sorgu geçmişine kayıt eklerken genel bir hata oluştu: {e}", "HISTORY_ADD_DB_GENERAL_ERR")
        traceback.print_exc()
        return False
    finally:
        if conn:
            conn.close()

def load_user_settings():
    """
    Kullanıcı ayarlarını UserSettings tablosundan yükler.
    Eksik ayarlar için varsayılan değerleri kullanır ve gerekirse veritabanına kaydeder.
    """
    default_settings = {
        "favorite_translator_ids": [],  # Liste olarak saklanacak, DB'ye JSON string olarak yazılacak
        "max_favorites_limit": 3        # Integer olarak saklanacak, DB'ye string olarak yazılabilir
    }
    loaded_settings = dict(default_settings) # Başlangıçta varsayılanları kopyala

    conn = None
    try:
        conn = sqlite3.connect(DATABASE_FILE)
        cursor = conn.cursor()
        cursor.execute("SELECT setting_key, setting_value FROM UserSettings")
        rows = cursor.fetchall()

        db_settings = {}
        for key, value_str in rows:
            db_settings[key] = value_str

        # Favori çevirmen ID'lerini yükle ve işle
        if "favorite_translator_ids" in db_settings:
            try:
                fav_ids_from_db = json.loads(db_settings["favorite_translator_ids"])
                if isinstance(fav_ids_from_db, list):
                    loaded_settings["favorite_translator_ids"] = fav_ids_from_db
                else:
                    cprint_debug(f"UYARI: 'favorite_translator_ids' DB'den liste olarak okunamadı. Varsayılan kullanılıyor.", "SETTINGS_LOAD_WARN")
                    # Varsayılan zaten [] olduğu için ekstra bir şey yapmaya gerek yok, ama DB'ye hatalı veriyi düzeltmek için save_user_settings çağrılabilir.
            except json.JSONDecodeError:
                cprint_debug(f"HATA: 'favorite_translator_ids' JSON verisi ('{db_settings['favorite_translator_ids']}') DB'den ayrıştırılamadı. Varsayılan kullanılıyor.", "SETTINGS_LOAD_JSON_ERR")
        
        # Maksimum favori limitini yükle ve işle
        if "max_favorites_limit" in db_settings:
            try:
                max_limit_from_db = int(db_settings["max_favorites_limit"])
                loaded_settings["max_favorites_limit"] = max(3, min(7, max_limit_from_db)) # 3-7 arasında sınırla
            except ValueError:
                cprint_debug(f"HATA: 'max_favorites_limit' değeri ('{db_settings['max_favorites_limit']}') DB'den integer'a çevrilemedi. Varsayılan kullanılıyor.", "SETTINGS_LOAD_VAL_ERR")
        
        # Eğer veritabanında hiç ayar yoksa (ilk çalıştırma gibi), varsayılanları kaydet
        if not rows:
            cprint_debug("Kullanıcı ayarları veritabanında bulunamadı. Varsayılan ayarlar oluşturuluyor ve kaydediliyor.", "SETTINGS_INIT")
            # Geçici olarak mevcut save_user_settings yerine doğrudan işlem yapıyoruz
            # çünkü save_user_settings'i bir sonraki adımda güncelleyeceğiz.
            # Bu kısım, save_user_settings güncellendikten sonra save_user_settings(default_settings) olarak değiştirilebilir.
            try:
                cursor.execute("INSERT OR REPLACE INTO UserSettings (setting_key, setting_value) VALUES (?, ?)",
                               ("favorite_translator_ids", json.dumps(default_settings["favorite_translator_ids"])))
                cursor.execute("INSERT OR REPLACE INTO UserSettings (setting_key, setting_value) VALUES (?, ?)",
                               ("max_favorites_limit", str(default_settings["max_favorites_limit"])))
                conn.commit()
            except sqlite3.Error as e_save:
                 cprint_debug(f"HATA: Varsayılan ayarlar UserSettings tablosuna kaydedilirken: {e_save}", "SETTINGS_SAVE_INIT_ERR")


        cprint_debug(f"Kullanıcı ayarları UserSettings tablosundan yüklendi: {loaded_settings}", "SETTINGS_LOAD_DB_SUCCESS")
        return loaded_settings

    except sqlite3.Error as e:
        cprint_debug(f"HATA: Kullanıcı ayarları UserSettings tablosundan yüklenirken SQLite hatası: {e}. Varsayılanlar kullanılıyor.", "SETTINGS_LOAD_DB_SQLITE_ERR")
        # Hata durumunda varsayılan ayarları döndür ve kaydetmeyi dene (eğer bağlantı varsa)
        if conn: # Eğer bağlantı açılabildiyse ama sorguda hata olduysa, varsayılanları kaydetmeye çalış.
            try:
                # Bu, save_user_settings güncellendiğinde oraya delege edilebilir.
                # Şimdilik, yukarıdaki gibi manuel ekleme.
                cursor_err_save = conn.cursor()
                cursor_err_save.execute("INSERT OR REPLACE INTO UserSettings (setting_key, setting_value) VALUES (?, ?)",
                               ("favorite_translator_ids", json.dumps(default_settings["favorite_translator_ids"])))
                cursor_err_save.execute("INSERT OR REPLACE INTO UserSettings (setting_key, setting_value) VALUES (?, ?)",
                               ("max_favorites_limit", str(default_settings["max_favorites_limit"])))
                conn.commit()
                cprint_debug("SQLite hatası sonrası varsayılan ayarlar UserSettings tablosuna kaydedildi.", "SETTINGS_SAVE_DEFAULT_ON_ERR")
            except sqlite3.Error as e_save_err:
                 cprint_debug(f"HATA: Hata sonrası varsayılan ayarlar UserSettings tablosuna kaydedilirken: {e_save_err}", "SETTINGS_SAVE_DEFAULT_ON_ERR_FAIL")
        return dict(default_settings) # Her zaman bir sözlük döndür
    except Exception as e_gen:
        cprint_debug(f"HATA: Kullanıcı ayarları yüklenirken genel bir hata oluştu: {e_gen}. Varsayılanlar kullanılıyor.", "SETTINGS_LOAD_DB_GENERAL_ERR")
        traceback.print_exc()
        return dict(default_settings) # Her zaman bir sözlük döndür
    finally:
        if conn:
            conn.close()

def save_user_settings(settings_data):
    """
    Verilen ayar sözlüğünü UserSettings tablosuna kaydeder.
    'INSERT OR REPLACE' kullanarak mevcut ayarları günceller veya yenilerini ekler.
    """
    if not isinstance(settings_data, dict):
        cprint_debug(f"HATA: save_user_settings fonksiyonuna geçersiz veri tipi gönderildi: {type(settings_data)}. Sözlük bekleniyordu.", "SETTINGS_SAVE_TYPE_ERR")
        return False

    conn = None
    try:
        conn = sqlite3.connect(DATABASE_FILE)
        cursor = conn.cursor()

        for key, value in settings_data.items():
            value_to_save_str = ""
            if key == "favorite_translator_ids":
                if isinstance(value, list):
                    value_to_save_str = json.dumps(value)
                else:
                    cprint_debug(f"UYARI: 'favorite_translator_ids' için beklenen tip liste değil: {type(value)}. Boş liste olarak kaydedilecek.", "SETTINGS_SAVE_WARN")
                    value_to_save_str = json.dumps([]) # Hatalı tip yerine boş liste
            elif key == "max_favorites_limit":
                try:
                    limit_int = int(value)
                    value_to_save_str = str(max(3, min(7, limit_int))) # 3-7 arasında sınırla ve string'e çevir
                except ValueError:
                    cprint_debug(f"UYARI: 'max_favorites_limit' için değer ('{value}') integer'a çevrilemedi. Varsayılan (3) olarak kaydedilecek.", "SETTINGS_SAVE_WARN_LIMIT")
                    value_to_save_str = str(3) # Hatalı değer yerine varsayılan
            else:
                # Diğer ayarlar için doğrudan string'e çevirmeyi deneyebiliriz.
                # Ancak şu an için sadece bilinen ayarları işliyoruz.
                # Bilinmeyen bir ayar gelirse, ya atlayabiliriz ya da hata verebiliriz.
                # Şimdilik bilinmeyen ayarları atlayalım veya loglayalım.
                cprint_debug(f"BİLGİ: Bilinmeyen ayar anahtarı ('{key}') save_user_settings içinde işlenmedi.", "SETTINGS_SAVE_UNKNOWN_KEY")
                continue # Bilinmeyen ayarı kaydetme

            # Ayarı veritabanına yaz
            cursor.execute("INSERT OR REPLACE INTO UserSettings (setting_key, setting_value) VALUES (?, ?)",
                           (key, value_to_save_str))
        
        conn.commit()
        cprint_debug(f"Kullanıcı ayarları UserSettings tablosuna başarıyla kaydedildi: {settings_data}", "SETTINGS_SAVE_DB_SUCCESS")
        return True

    except sqlite3.Error as e:
        if conn:
            conn.rollback()
        cprint_debug(f"HATA: Kullanıcı ayarları UserSettings tablosuna kaydedilirken SQLite hatası: {e}", "SETTINGS_SAVE_DB_SQLITE_ERR")
        return False
    except Exception as e_gen:
        if conn:
            conn.rollback()
        cprint_debug(f"HATA: Kullanıcı ayarları kaydedilirken genel bir hata oluştu: {e_gen}", "SETTINGS_SAVE_DB_GENERAL_ERR")
        traceback.print_exc()
        return False
    finally:
        if conn:
            conn.close()


def load_favorite_ayets():
    """
    Favori ayetleri veritabanındaki FavoriAyetler tablosundan yükler.
    Her favori ayet için sure numarası, ayet numarası, sure adı ve Arapça metnini alır.
    Sonuçları global favorite_ayets_list deque'sine yükler.
    """
    global favorite_ayets_list # Bu global listeyi güncelleyeceğiz
    
    loaded_favs_tuples = []
    conn = None
    try:
        conn = sqlite3.connect(DATABASE_FILE)
        cursor = conn.cursor()

        # Favori ayetleri, Ayahs ve Surahs tablolarıyla birleştirerek çek.
        # eklenme_zamani'na göre sırala (en eskiden en yeniye),
        # böylece deque maxlen'e ulaştığında en eski favoriler atılır (eğer bu isteniyorsa)
        # veya deque'nin doğal davranışı (sondan maxlen kadarını tutma) en yenileri tutar.
        query = """
            SELECT
                A.surah_number,
                A.ayah_number_in_surah,
                S.name AS surah_name,
                A.arabic_text
            FROM
                FavoriAyetler FA
            JOIN
                Ayahs A ON FA.ayah_db_id = A.ayah_db_id
            JOIN
                Surahs S ON A.surah_number = S.surah_number
            ORDER BY
                FA.eklenme_zamani ASC;
        """
        # MAX_FAVORITE_AYETS_SIZE limiti deque tarafından yönetileceği için SQL'de limit koymuyoruz.
        # Tüm favorileri çekip deque'ye veriyoruz.
        cursor.execute(query)
        rows = cursor.fetchall()

        for row in rows:
            # Gelen verinin tiplerini doğrula/dönüştür (int, int, str, str)
            try:
                s_no = int(row[0])
                a_no = int(row[1])
                s_name = str(row[2])
                a_text = str(row[3])
                loaded_favs_tuples.append((s_no, a_no, s_name, a_text))
            except (ValueError, TypeError, IndexError) as e:
                cprint_debug(f"UYARI: Favori ayet yüklenirken veritabanından gelen hatalı satır formatı: {row}. Hata: {e}", "FAV_AYET_LOAD_DB_ROW_ERR")
        
        # favorite_ayets_list deque'sini yüklenen verilerle güncelle
        # Deque, maxlen'i aşarsa sondaki (en yeni eklenen) öğeleri tutacaktır.
        favorite_ayets_list = collections.deque(loaded_favs_tuples, maxlen=MAX_FAVORITE_AYETS_SIZE)

        cprint_debug(f"Favori ayetler veritabanından başarıyla yüklendi ({len(favorite_ayets_list)} kayıt).", "FAV_AYET_LOAD_DB_SUCCESS")

    except sqlite3.Error as e:
        cprint_debug(f"HATA: Favori ayetler veritabanından yüklenirken SQLite hatası: {e}", "FAV_AYET_LOAD_DB_SQLITE_ERR")
        favorite_ayets_list = collections.deque(maxlen=MAX_FAVORITE_AYETS_SIZE) # Hata durumunda boşalt
    except Exception as e_gen:
        cprint_debug(f"HATA: Favori ayetler yüklenirken genel bir hata oluştu: {e_gen}", "FAV_AYET_LOAD_DB_GENERAL_ERR")
        traceback.print_exc()
        favorite_ayets_list = collections.deque(maxlen=MAX_FAVORITE_AYETS_SIZE) # Hata durumunda boşalt
    finally:
        if conn:
            conn.close()
            
    return list(favorite_ayets_list)


def get_random_ayah_info():
    """
    Veritabanındaki Surahs tablosundan rastgele bir sure numarası ve
    o sureden rastgele bir ayet numarası seçer.

    Returns:
        tuple: (rastgele_sure_no, rastgele_ayet_no) formatında bir demet (int, int).
               Surahs tablosu boşsa veya bir hata oluşursa (None, None) döner.
    """
    conn = None
    try:
        conn = sqlite3.connect(DATABASE_FILE)
        cursor = conn.cursor()

        # Sure numaralarını ve ayet sayılarını veritabanından çek
        cursor.execute("SELECT surah_number, ayah_count FROM Surahs")
        all_surahs_data = cursor.fetchall()  # Örn: [(1, 7), (2, 286), ...]

        if not all_surahs_data:
            cprint_debug("UYARI: get_random_ayah_info - Surahs tablosunda veri bulunamadı. Rastgele ayet seçilemiyor.", "RANDOM_AYAH_EMPTY_DB")
            return None, None

        # Rastgele bir sure seç (all_surahs_data listesinden)
        selected_surah_tuple = random.choice(all_surahs_data)
        random_surah_no = int(selected_surah_tuple[0])
        max_ayah_for_selected_surah = int(selected_surah_tuple[1])

        if max_ayah_for_selected_surah <= 0:
            # Bu durum normalde olmamalı ama veritabanı tutarlılığı için kontrol
            cprint_debug(f"UYARI: get_random_ayah_info - Seçilen sure ({random_surah_no}) için ayet sayısı ({max_ayah_for_selected_surah}) geçersiz. Tekrar deneniyor...", "RANDOM_AYAH_INVALID_COUNT")
            # Basit bir özyineleme veya farklı bir sure seçme mekanizması eklenebilir. Şimdilik None dönüyoruz.
            # Veya fonksiyonu tekrar çağırabiliriz, ancak sonsuz döngü riskine dikkat etmeli.
            # Güvenli olması için, eğer tüm surelerin ayet sayısı 0 ise diye bir kontrol daha geniş kapsamlı olurdu.
            # Şimdilik bu nadir durum için None dönüyoruz.
            return None, None 

        # Seçilen sureden rastgele bir ayet numarası seç
        random_ayet_no = random.randint(1, max_ayah_for_selected_surah)
        
        cprint_debug(f"Rastgele ayet seçildi: Sure No: {random_surah_no}, Ayet No: {random_ayet_no}", "RANDOM_AYAH_SELECTED")
        return random_surah_no, random_ayet_no

    except sqlite3.Error as e:
        cprint_debug(f"HATA: get_random_ayah_info veritabanı hatası: {e}", "RANDOM_AYAH_DB_ERR")
        return None, None
    except ImportError: # random modülü import edilemezse
        cprint_debug("HATA: get_random_ayah_info - 'random' modülü yüklenemedi.", "RANDOM_AYAH_IMPORT_ERR")
        return None, None
    except Exception as e_gen:
        cprint_debug(f"HATA: get_random_ayah_info genel hata: {e_gen}", "RANDOM_AYAH_GEN_ERR")
        traceback.print_exc()
        return None, None
    finally:
        if conn:
            conn.close()


def get_ayah_words_from_db(sure_no, ayet_no):
    """
    Verilen sure numarası ve ayet numarasına ait kelime kelime anlamları
    veritabanındaki AyahWords tablosundan çeker.

    Args:
        sure_no (int): Sure numarası.
        ayet_no (int): Ayet numarası.

    Returns:
        list: [(arabic_word, translation_word, word_order), ...] formatında
              kelime listesi. Bulunamazsa None.
    """
    if not isinstance(sure_no, int) or not isinstance(ayet_no, int):
        cprint_debug(f"HATA: get_ayah_words_from_db - sure_no ve ayet_no integer olmalıdır. Alınan: S:{sure_no} A:{ayet_no}", "WORDS_DB_PARAM_ERR")
        return None

    conn = None
    ayah_db_id = None
    try:
        conn = sqlite3.connect(DATABASE_FILE)
        cursor = conn.cursor()

        # 1. sure_no ve ayet_no'dan ayah_db_id'yi bul
        cursor.execute("SELECT ayah_db_id FROM Ayahs WHERE surah_number = ? AND ayah_number_in_surah = ?", (sure_no, ayet_no))
        row = cursor.fetchone()
        if row:
            ayah_db_id = row[0]
        else:
            cprint_debug(f"BİLGİ: {sure_no}:{ayet_no} için Ayahs tablosunda ayah_db_id bulunamadı.", "WORDS_DB_AYAH_ID_NOT_FOUND")
            return None # Ayet bulunamadıysa kelime de yoktur

        # 2. ayah_db_id kullanarak AyahWords tablosundan kelimeleri çek
        cursor.execute("""
            SELECT arabic_word, translation_word, word_order
            FROM AyahWords
            WHERE ayah_db_id = ?
            ORDER BY word_order ASC
        """, (ayah_db_id,))
        
        word_rows = cursor.fetchall()

        if not word_rows:
            cprint_debug(f"BİLGİ: {sure_no}:{ayet_no} (ayah_db_id: {ayah_db_id}) için AyahWords tablosunda kelime bulunamadı.", "WORDS_DB_NOT_FOUND")
            return None 

        ayah_words_list = []
        for r_arabic_word, r_translation_word, r_word_order in word_rows:
            # Veri tiplerinin doğruluğunu varsayıyoruz (DB'den geliyor)
            # ama None kontrolü yapılabilir.
            ayah_words_list.append((
                str(r_arabic_word) if r_arabic_word is not None else "",
                str(r_translation_word) if r_translation_word is not None else "",
                int(r_word_order) if r_word_order is not None else 0 # word_order'ın None olmaması gerekir
            ))
        
        cprint_debug(f"{sure_no}:{ayet_no} için {len(ayah_words_list)} kelime AyahWords tablosundan yüklendi.", "WORDS_DB_LOADED")
        return ayah_words_list

    except sqlite3.Error as e:
        cprint_debug(f"HATA: get_ayah_words_from_db ({sure_no}:{ayet_no}) - SQLite hatası: {e}", "WORDS_DB_SQLITE_ERR")
        return None
    except Exception as e_gen:
        cprint_debug(f"HATA: get_ayah_words_from_db ({sure_no}:{ayet_no}) - Genel hata: {e_gen}", "WORDS_DB_GENERAL_ERR")
        traceback.print_exc()
        return None
    finally:
        if conn:
            conn.close()

def get_complete_ayah_details_from_db(sure_no, ayet_no):
    """
    Verilen sure ve ayet numarası için tüm detayları veritabanından çeker.
    Sonuçları ayet_cache'te önbelleğe alır.
    """
    global ayet_cache # Global önbelleği kullan

    if not isinstance(sure_no, int) or not isinstance(ayet_no, int):
        cprint_debug(f"HATA: get_complete_ayah_details_from_db - sure_no ve ayet_no integer olmalıdır. Alınan: S:{sure_no} A:{ayet_no}", "GET_DETAILS_PARAM_ERR")
        return {
            "url": None, "sure_no": sure_no, "ayet_no": ayet_no, "sure_adi": "Hatalı Giriş",
            "ayet_numarasi_str": f"{ayet_no}. Ayet", "arapca_metin": None,
            "transliterasyon": {"yazar": None, "metin": None},
            "mealler": [], "kelimeler": [], "error": "Geçersiz sure veya ayet numarası."
        }

    cache_key = (sure_no, ayet_no)
    if cache_key in ayet_cache:
        cprint_debug(f"Ayet detayları {sure_no}:{ayet_no} için önbellekten yüklendi.", "CACHE_HIT_DETAILS")
        return ayet_cache[cache_key]

    conn = None
    try:
        conn = sqlite3.connect(DATABASE_FILE)
        cursor = conn.cursor()

        # Temel ayet bilgilerini ve ayah_db_id'yi çek
        cursor.execute("""
            SELECT ayah_db_id, arabic_text, transliteration
            FROM Ayahs
            WHERE surah_number = ? AND ayah_number_in_surah = ?
        """, (sure_no, ayet_no))
        ayah_row = cursor.fetchone()

        if not ayah_row:
            error_message = f"{sure_no}:{ayet_no} için ayet bulunamadı."
            cprint_debug(error_message, "GET_DETAILS_AYAH_NOT_FOUND")
            result = {
                "url": None, "sure_no": sure_no, "ayet_no": ayet_no, "sure_adi": "Bulunamadı",
                "ayet_numarasi_str": f"{ayet_no}. Ayet", "arapca_metin": None,
                "transliterasyon": {"yazar": None, "metin": None},
                "mealler": [], "kelimeler": [], "error": error_message
            }
            ayet_cache[cache_key] = result # Başarısız sonucu da cache'leyebiliriz (kısa süreliğine) veya cache'lemeyebiliriz. Şimdilik cache'liyoruz.
            return result

        ayah_db_id, arabic_text_db, transliteration_db = ayah_row
        arabic_text_db = arabic_text_db if arabic_text_db is not None else ""
        transliteration_db = transliteration_db if transliteration_db is not None else ""

        # Sure adını çek
        cursor.execute("SELECT name FROM Surahs WHERE surah_number = ?", (sure_no,))
        surah_row = cursor.fetchone()
        surah_name_db = surah_row[0] if surah_row else "Bilinmeyen Sure"

        # Mealleri çek
        mealler_list = []
        cursor.execute("""
            SELECT TRL.name, TRL.site_id, TR.translation_text
            FROM Translations TR
            JOIN Translators TRL ON TR.translator_db_id = TRL.translator_db_id
            WHERE TR.ayah_db_id = ?
        """, (ayah_db_id,))
        translation_rows = cursor.fetchall()
        for tr_name, tr_site_id, tr_text in translation_rows:
            mealler_list.append({
                "id": str(tr_site_id) if tr_site_id else "", # site_id eski yapıda ID olarak kullanılıyordu
                "yazar_raw": str(tr_name) if tr_name else "Bilinmeyen Mütercim",
                "metin": str(tr_text) if tr_text else ""
            })

        kelimeler_list = get_ayah_words_from_db(sure_no, ayet_no)

        if kelimeler_list:
            kelimeler_list_sorted = sorted(kelimeler_list, key=lambda x: x[2], reverse=True)
            kelimeler_list = kelimeler_list_sorted

        if kelimeler_list is None:
            kelimeler_list = []

        ayet_details = {
            "url": None, # Web kazıma artık yok
            "sure_no": sure_no,
            "ayet_no": ayet_no,
            "ayah_db_id": ayah_db_id,
            "sure_adi": surah_name_db,
            "ayet_numarasi_str": f"{ayet_no}. Ayet", # main.py'nin beklentisine göre ayarlanabilir (örn: "{ayet_no}.A")
            "arapca_metin": arabic_text_db,
            "transliterasyon": {
                "yazar": None, # Veritabanında transliterasyon için yazar bilgisi yok
                "metin": transliteration_db
            },
            "mealler": mealler_list,
            "kelimeler": kelimeler_list,
            "error": None
        }

        ayet_cache[cache_key] = ayet_details # Başarılı sonucu önbelleğe al
        cprint_debug(f"Ayet detayları {sure_no}:{ayet_no} için veritabanından çekildi ve önbelleğe alındı.", "GET_DETAILS_DB_SUCCESS")
        return ayet_details

    except sqlite3.Error as e:
        error_message = f"get_complete_ayah_details_from_db ({sure_no}:{ayet_no}) - SQLite hatası: {e}"
        cprint_debug(error_message, "GET_DETAILS_SQLITE_ERR")
        return {
            "url": None, "sure_no": sure_no, "ayet_no": ayet_no, "sure_adi": "Veritabanı Hatası",
            "ayet_numarasi_str": f"{ayet_no}. Ayet", "arapca_metin": None,
            "transliterasyon": {"yazar": None, "metin": None},
            "mealler": [], "kelimeler": [], "error": error_message
        }
    except Exception as e_gen:
        error_message = f"get_complete_ayah_details_from_db ({sure_no}:{ayet_no}) - Genel hata: {e_gen}"
        cprint_debug(error_message, "GET_DETAILS_GENERAL_ERR")
        traceback.print_exc()
        return {
            "url": None, "sure_no": sure_no, "ayet_no": ayet_no, "sure_adi": "Genel Hata",
            "ayet_numarasi_str": f"{ayet_no}. Ayet", "arapca_metin": None,
            "transliterasyon": {"yazar": None, "metin": None},
            "mealler": [], "kelimeler": [], "error": error_message
        }
    finally:
        if conn:
            conn.close()

POS_TAG_MAP_CORPUS = {
    "N": "İsim", "PN": "Özel İsim", "ADJ": "Sıfat", "V": "Fiil",
    "PRON": "Zamir", "REL": "İlgi Zamiri (İsm-i Mevsûl)", "DEM": "İşaret Zamiri/Sıfatı",
    "DET": "Belirteç (ال)",
    "P": "Harf-i Cer / Edat", "CONJ": "Bağlaç (Atıf)",
    "NEG": "Olumsuzluk Edatı", "ACC": "Nasb/Te'kid Harfi", "VOC": "Nida Harfi",
    "PART": "Diğer Edat/Parçacık", "FUT": "Gelecek Zaman Edatı", "INTG": "Soru Edatı",
    "EMPH": "Vurgu/Tekid Edatı", "COND": "Şart Edatı", "T": "Zaman Zarfı",
    "LOC": "Mekan Zarfı", "INL": "Hurûf-u Mukattaa", "CERT": "Kesinlik Edatı (Tahkik)",
    "PRO": "Yasaklama Edatı (Nehy)", "SUB": "Mastar Edatı", "REM": "Sonuç/Başlangıç Edatı",
    "RSLT": "Sonuç Edatı (Fa-i Cevabiye/RSLT)",
    "RET": "İstidrâk Edatı", "RES": "Cevap/İstisnâ Edatı", "EXP": "İstisnâ Edatı",
    "EQ": "Denklik/Soru Edatı", "SP": "Özel Parçacık Grubu",
    "PREV": "Önleyici Harf", "INC": "Başlangıç/Uyarı Harfi", "EXH": "Teşvik Harfi",
    "SUR": "Sürpriz/Ani Durum Harfi", "AMD": "Düzeltme Harfi", "ANS": "Cevap Harfi",
    "VN": "Mastar (Fiilden İsim)", "ACT PCPL": "İsm-i Fâil (Etken Ortaç)",
    "PASS PCPL": "İsm-i Mef'ûl (Edilgen Ortaç)",
    "NUM": "Sayı"
}

GRAMMAR_FEATURE_MAP = {
    "M": "Eril", "F": "Dişil",
    "SG": "Tekil", "S": "Tekil", "DU": "İkil", "D": "İkil", "PL": "Çoğul", "P": "Çoğul",
    "1": "1.Şahıs", "2": "2.Şahıs", "3": "3.Şahıs",
    "1S": "1.T.Şahıs", "1P": "1.Ç.Şahıs",
    "2MS": "2.E.T.Şahıs", "2FS": "2.D.T.Şahıs", "2D": "2.İkil Şahıs",
    "2MP": "2.E.Ç.Şahıs", "2FP": "2.D.Ç.Şahıs",
    "3MS": "3.E.T.Şahıs", "3FS": "3.D.T.Şahıs", "3D": "3.İkil Şahıs",
    "3MP": "3.E.Ç.Şahıs", "3FP": "3.D.Ç.Şahıs",
    "MS": "E.Tekil", "FS": "D.Tekil", "MP": "E.Çoğul", "FP": "D.Çoğul", "MD": "E.İkil", "FD": "D.İkil",
    "NOM": "Merfû'", "ACC": "Mansûb", "GEN": "Mecrûr",
    "ACT": "Etken", "PASS": "Edilgen",
    "IMPV": "Emir", "PERF": "Mâzî", "IMPF": "Muzâri",
    "IND": "Merfû' (Muzâri)", "SUBJ": "Mansûb (Muzâri)", "JUS": "Meczûm (Muzâri)", "ENG": "Tekidli (Muzâri)",
    "MOOD:IND": "Muzâri-Merfû'", "MOOD:SUBJ": "Muzâri-Mansûb'", "MOOD:JUS": "Muzâri-Meczûm'", "MOOD:ENG": "Tekidli Muzâri",
    "I": "I.Bab", "(I)": "I.Bab (Sülâsî)", "II": "II.Bab", "(II)": "II.Bab (فعّل)",
    "III": "III.Bab", "(III)": "III.Bab (فاعل)", "IV": "IV.Bab", "(IV)": "IV.Bab (أفعل)",
    "V": "V.Bab", "(V)": "V.Bab (تفعّل)", "VI": "VI.Bab", "(VI)": "VI.Bab (تفاعل)",
    "VII": "VII.Bab", "(VII)": "VII.Bab (انفعل)", "VIII": "VIII.Bab", "(VIII)": "VIII.Bab (افتعل)",
    "IX": "IX.Bab", "(IX)": "IX.Bab (افعلّ)", "X": "X.Bab", "(X)": "X.Bab (استفعل)",
    "XI": "XI.Bab", "(XI)": "XI.Bab (افعالّ)", "XII": "XII.Bab", "(XII)": "XII.Bab (افعوعل)",
    "INDEF": "Nekre", "DEF": "Ma'rife",
    "VN": "Mastar", "PCPL": "Ortaç",
    "SP:KAAN": "Kâne Grubu", "SP:<IN~": "İnne Grubu", "SP:INNE": "İnne Grubu",
    "PRON:1S": "Bitişik Zamir (Ben)", "PRON:1P": "Bitişik Zamir (Biz)",
    "PRON:2MS": "Bitişik Zamir (Sen, Eril)", "PRON:2FS": "Bitişik Zamir (Sen, Dişil)",
    "PRON:2MP": "Bitişik Zamir (Siz, Eril Çoğul)", "PRON:2FP": "Bitişik Zamir (Siz, Dişil Çoğul)",
    "PRON:2D": "Bitişik Zamir (Siz İkiniz)",
    "PRON:3MS": "Bitişik Zamir (O, Eril)", "PRON:3FS": "Bitişik Zamir (O, Dişil)",
    "PRON:3MP": "Bitişik Zamir (Onlar, Eril Çoğul)", "PRON:3FP": "Bitişik Zamir (Onlar, Dişil Çoğul)",
    "PRON:3D": "Bitişik Zamir (O İkisi)",
    "VOC": "Nida Harfi", "REM": "Sonuç/Başlangıç Edatı",
    "F:REM": "Fa (Sonuç/Başlangıç Edatı)", "F:CONJ": "Fa (Atıf Edatı)",
    "L:P": "Lam Harfi (Harf-i Cer)", "BI:P": "Bi Harfi (Harf-i Cer)",
    "A:INTG": "Soru Edatı (أ)", "AL": "Harf-i Ta'rif (ال)"
}

def cprint_debug(text, prefix="DEBUG"):
    print(f"[{prefix}] {time.strftime('%Y-%m-%d %H:%M:%S')} - {text}")

def clean_morph_string(value_str):
    if not value_str or str(value_str).lower() == 'none':
        return ""
    cleaned = str(value_str).replace("&lt;", "<").replace("&gt;", ">").replace("&amp;", "&")
    return cleaned.strip()

def get_morphology_and_transliteration_from_db_segments(segments):
    if not segments:
        cprint_debug("UYARI (get_morphology_from_segments): İşlenecek segment (satır) bulunamadı.", "MORPH_PROCESS_WARN")
        return "-", "-", "-", "N/A"
    
    try: 
        processed_segment = segments[0] # Her kelime için tek bir satır (segment) bekliyoruz

        # Sütun indeksleri fetch_and_process_word_segments'teki SELECT sırasına göre:
        # seg[4]: primary_lemma_buckwalter (Transliterasyon/Lemma için)
        # seg[5]: primary_pos (Ana POS etiketi için)
        # seg[9]: primary_root (Yedek veya birincil kök için)
        # seg[10]: features_column (Veritabanındaki ham özellikler, JSON string)
        # seg[11]: morphology_original (Ayrıştırılacak ana morfoloji dizesi)

        transliteration_str = clean_morph_string(str(processed_segment[4])) or "N/A"
        
        primary_pos_tag = str(processed_segment[5]).strip().upper()
        tur_anlasilir_str = POS_TAG_MAP_CORPUS.get(primary_pos_tag, primary_pos_tag) if primary_pos_tag else "-"

        combined_root = "-"
        all_features_set = set() 

        # Adım 1: morphology_original (seg[11]) dizesini ayrıştır
        morph_orig_str = clean_morph_string(str(processed_segment[11]))
        if morph_orig_str:
            # Kökü bul (ROOT:XXX)
            root_match = re.search(r'ROOT:(\S+)', morph_orig_str, re.IGNORECASE)
            if root_match:
                combined_root = root_match.group(1).strip()
            
            # Lemmayı bul ve özellik olarak ekle (LEM:XXX)
            lemma_match = re.search(r'LEM:(\S+)', morph_orig_str, re.IGNORECASE)
            if lemma_match:
                lemma_val = lemma_match.group(1).strip()
                # Lemma bilgisini "Lemma: [değer]" formatında ekle
                # Eğer GRAMMAR_FEATURE_MAP'te "LEM" veya benzeri bir anahtarınız varsa onu kullanabilirsiniz.
                # Şimdilik açıkça belirtiyoruz.
                all_features_set.add(f"Lemma: {lemma_val}")

            # morphology_original'dan diğer etiketleri/özellikleri çıkar
            # Örnek formatlar: "Al+ POS:ADJ MS GEN", "bi+ P M GEN", "POS:V IMPF (X) 1MP"
            # Parçaları boşluklara göre ayıralım
            parts_from_morph_orig = morph_orig_str.split(' ')
            for part in parts_from_morph_orig:
                part_cleaned = part.strip().upper()
                if not part_cleaned: continue

                # Zaten işlenmiş ROOT: ve LEM: kısımlarını atla
                if part_cleaned.startswith("ROOT:") or part_cleaned.startswith("LEM:"):
                    continue
                
                # POS:X formatındaki kısımları atla (ana POS'u primary_pos'tan alıyoruz)
                if part_cleaned.startswith("POS:"):
                    continue

                # Ön ekleri (Al+, wa+, bi+) veya diğer tekil etiketleri işle
                # Parantez içindeki Roma rakamları (örn: (IV)) gibi yapıları koru
                tag_to_map = part_cleaned
                
                # Eğer etiketin sonunda "+" varsa ve bu GRAMMAR_FEATURE_MAP'te özel bir anlam ifade etmiyorsa,
                # "+" işaretini kaldırıp deneyebiliriz. Örn: "f:REM+" -> "f:REM"
                # Şimdilik, haritada doğrudan eşleşme arıyoruz.
                # GRAMMAR_FEATURE_MAP'teki anahtarların bu "+" işaretlerini içerip içermediğine bağlı.
                # Örneğin, GRAMMAR_FEATURE_MAP'te "F:REM" varsa, "F:REM+" eşleşmez.
                # Bu nedenle, eğer haritanızda "F:REM" gibi anahtarlar varsa, "+" temizliği gerekebilir:
                # if tag_to_map.endswith('+') and tag_to_map[:-1] in GRAMMAR_FEATURE_MAP:
                #    tag_to_map = tag_to_map[:-1]
                
                decoded_feature = GRAMMAR_FEATURE_MAP.get(tag_to_map)
                if decoded_feature:
                    all_features_set.add(decoded_feature)
                elif tag_to_map and tag_to_map not in POS_TAG_MAP_CORPUS: 
                    # Haritada yoksa ve birincil POS değilse, potansiyel yeni bir özellik olabilir.
                    # Çok fazla gürültü eklememesi için bu kısmı dikkatli kullanmak gerekebilir.
                    # Şimdilik bilinmeyenleri doğrudan eklemeyelim, sadece loglayabiliriz.
                    # cprint_debug(f"INFO (MORPH_ORIG): Bilinmeyen etiket '{tag_to_map}' morphology_original'dan geldi, değerlendiriliyor.", "MORPH_ORIG_UNKNOWN")
                    pass # İsteğe bağlı: all_features_set.add(tag_to_map)

        # Adım 2: features_column (seg[10]) JSON listesini ayrıştır (eğer varsa)
        features_json_data = processed_segment[10] # Bu artık ham JSON string'i veya Python listesi DEĞİL, doğrudan SQLite'tan gelen değer.
                                                 # SQLite Python API'si JSON string'lerini otomatik ayrıştırmaz.
        if features_json_data and isinstance(features_json_data, str): # String ise JSON parse etmeyi dene
            try:
                features_list_from_json = json.loads(features_json_data) 
                if isinstance(features_list_from_json, list):
                    for feature_item_raw in features_list_from_json:
                        feature_item = clean_morph_string(str(feature_item_raw)).strip().upper()
                        if not feature_item: continue
                        
                        # Örnek: "bi" gibi etiketler veya "M", "GEN" gibi özellikler olabilir
                        # Bunlar bazen GRAMMAR_FEATURE_MAP'te doğrudan olabilir.
                        decoded_feature = GRAMMAR_FEATURE_MAP.get(feature_item)
                        if decoded_feature:
                            all_features_set.add(decoded_feature)
                        elif feature_item and feature_item not in POS_TAG_MAP_CORPUS:
                            # JSON içindeki bilinmeyen etiketler (eğer birincil POS değilse)
                            # cprint_debug(f"INFO (FEATURES_JSON): Bilinmeyen etiket '{feature_item}' features_json'dan geldi.", "JSON_TAG_UNKNOWN")
                            all_features_set.add(feature_item) # Olduğu gibi ekle, belki anlamlıdır
                            
            except json.JSONDecodeError:
                cprint_debug(f"UYARI: features sütunundaki JSON verisi ('{features_json_data}') ayrıştırılamadı.", "MORPH_JSON_ERR")
            except Exception as e_json:
                 cprint_debug(f"HATA: features sütunu ('{features_json_data}') işlenirken: {e_json}", "MORPH_JSON_PROC_ERR")

        # Adım 3: Kök için yedek kontrol (eğer morphology_original'dan alınamadıysa)
        if combined_root == "-": # veya combined_root boşsa
            combined_root = clean_morph_string(str(processed_segment[9])) or "-" # primary_root'tan al
        
        # Gramer detaylarını oluştur
        gramer_detay_str = ", ".join(sorted(list(f for f in all_features_set if f and f.strip()))) if all_features_set else "-"
            
        cprint_debug(f"MORPH_PROCESSED_FINAL: Kok='{combined_root}', Tur='{tur_anlasilir_str}', Gramer='{gramer_detay_str}', Translit='{transliteration_str}'", "MORPH_FINAL")
        return combined_root, tur_anlasilir_str, gramer_detay_str, transliteration_str

    except Exception as e_inner: 
        cprint_debug(f"HATA (get_morphology_and_transliteration_from_db_segments): Segment işlenirken genel hata: {e_inner}", "MORPH_PROCESS_OVERALL_ERR")
        traceback.print_exc()
        return "Hata", "Hata", "Hata", "Hata"


def fetch_and_process_word_segments(sure_no, ayet_no, kelime_sira_ipucu, aranan_arapca_token_kuran_com=None):
    cprint_debug(f"AYAT_UTILS_FETCH_ENTRY (CorpusWordDetails): DB='{DATABASE_FILE}', S:{sure_no}, A:{ayet_no}, İpucuSıra:{kelime_sira_ipucu}", "UTILS_ENTRY_CORPUS")

    if not os.path.exists(DATABASE_FILE):
        cprint_debug(f"HATA: Veritabanı dosyası bulunamadı: {DATABASE_FILE}", "DB_ACCESS_ERROR")
        return "-", "-", "-", "N/A"

    conn = None
    segments = []
    try:
        conn = sqlite3.connect(DATABASE_FILE)
        cursor = conn.cursor()
        
        target_word_order = kelime_sira_ipucu
        
        query = """
            SELECT
                A.surah_number,                     -- 0: Sadece bağlamsal
                A.ayah_number_in_surah,             -- 1: Sadece bağlamsal
                CWD.word_order_in_ayah AS word_num, -- 2: Kelime sırası
                1 AS part_num,                      -- 3: Varsayılan (her satır bir segment/token)
                CWD.primary_lemma_buckwalter AS token_transliterated, -- 4: Transliterasyon/Lemma (Buckwalter)
                CWD.primary_pos AS pos_short,       -- 5: Birincil POS etiketi
                'TOKEN' AS morphology_tag,          -- 6: Varsayılan etiket (STEM/PREFIX bilgisi yoksa)
                CWD.primary_pos AS detailed_pos,    -- 7: Detaylı POS (şimdilik primary_pos)
                CWD.primary_lemma_buckwalter AS lemma, -- 8: Lemma (Buckwalter)
                CWD.primary_root AS root,           -- 9: Birincil Kök
                CWD.features AS features_json,      -- 10: Özellikler (JSON string)
                CWD.morphology_original             -- 11: YENİ EKLENEN ORİJİNAL MORFOLOJİ DİZESİ
            FROM CorpusWordDetails CWD
            JOIN Ayahs A ON CWD.ayah_db_id = A.ayah_db_id
            WHERE A.surah_number = ? AND A.ayah_number_in_surah = ? AND CWD.word_order_in_ayah = ?;
        """ 
        cursor.execute(query, (sure_no, ayet_no, target_word_order))
        segments = cursor.fetchall()

    except sqlite3.Error as e:
        cprint_debug(f"SQLite Hatası (CorpusWordDetails'den Segment Çekerken S:{sure_no} A:{ayet_no} W_Sıra:{target_word_order}): {e}", "DB_CORPUS_QUERY_ERROR")
        return "DB Hatası", "DB Hatası", "DB Hatası", "N/A"
    finally:
        if conn:
            conn.close()

    if not segments:
        cprint_debug(f"UYARI: Veritabanında (CorpusWordDetails) segment bulunamadı (S:{sure_no}, A:{ayet_no}, W_Order:{target_word_order}).", "DB_NO_CORPUS_SEGMENTS")
        return "-", "-", "-", "N/A"
            
    return get_morphology_and_transliteration_from_db_segments(segments)

def load_quran_corpus_data():
    if not os.path.exists(DATABASE_FILE):
        cprint_debug(f"HATA: SQLite veritabanı dosyası ('{DATABASE_FILE}') bulunamadı.", "CORPUS_LOAD_FAIL")
        return False
    try:
        conn = sqlite3.connect(DATABASE_FILE)
        cursor = conn.cursor()
        # TABLO ADINI GÜNCELLEYİN: WordSegments -> CorpusWordDetails
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='CorpusWordDetails';")
        if not cursor.fetchone():
            conn.close()
            cprint_debug(f"HATA: SQLite veritabanında 'CorpusWordDetails' tablosu bulunamadı.", "CORPUS_LOAD_FAIL")
            return False
        conn.close()
        cprint_debug(f"SQLite veritabanı ('{DATABASE_FILE}') başarıyla doğrulandı (CorpusWordDetails var).", "CORPUS_LOAD_SUCCESS")
        return True
    except sqlite3.Error as e:
        cprint_debug(f"HATA: SQLite veritabanına ('{DATABASE_FILE}') bağlanırken hata oluştu: {e}", "CORPUS_LOAD_ERROR")
        return False
