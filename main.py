# main.py
import os
# os.environ['KIVY_TEXT'] = 'pango'

from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.screenmanager import ScreenManager, Screen, FadeTransition
from kivy.properties import ObjectProperty, StringProperty, ListProperty, NumericProperty, BooleanProperty, DictProperty
from kivy.lang import Builder
from kivy.clock import Clock
from kivy.event import EventDispatcher
from kivy.app import App
import threading
import collections 
import traceback
import sqlite3 
import platform

from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.popup import Popup
from kivy.uix.scrollview import ScrollView
from kivy.uix.gridlayout import GridLayout
from kivy.uix.textinput import TextInput
from kivy.uix.togglebutton import ToggleButton
from kivy.uix.slider import Slider
from kivy.metrics import dp
from kivy.core.clipboard import Clipboard
from kivy.uix.recycleview import RecycleView
from kivy.uix.recycleboxlayout import RecycleBoxLayout
from kivy.uix.recycleview.views import RecycleDataViewBehavior
from kivy.uix.behaviors import FocusBehavior
from kivy.uix.recycleview.layout import LayoutSelectionBehavior

from functools import partial
import ayat_utils 

Builder.load_file('kuran_app.kv') 

DEFAULT_READ_MODE_HOCA_IDS = ["besimatalay", "ismailyakit", "bayraktar"]
STAR_EMPTY_IMG = 'images/star_empty.png'
STAR_FILLED_IMG = 'images/star_filled.png'
HEART_EMPTY_IMG = 'images/heart_empty.png'
HEART_FILLED_IMG = 'images/heart_filled.png'

class SureSubjectsPopup(Popup):
    popup_title = StringProperty("Sure Konuları")
    subjects_list_data = ListProperty([])  # RecycleView için veri listesi
    read_mode_screen_ref = ObjectProperty(None) # ReadModeScreen'e referans
    target_sure_no = NumericProperty(0)
    target_sure_name = StringProperty('')

    def __init__(self, sure_no, sure_name, read_mode_ref, **kwargs):
        super().__init__(**kwargs)
        self.target_sure_no = int(sure_no)
        self.target_sure_name = str(sure_name)
        self.popup_title = f"[{self.target_sure_name} Suresi] Konuları"
        self.read_mode_screen_ref = read_mode_ref
        # Clock.schedule_once(self.populate_subjects) # KV yüklendikten sonra populate et
        # on_open içinde populate etmek daha güvenli olabilir, ids'lere erişim için
    
    def on_open(self):
        """ Popup açıldığında konuları yükle ve RV callback'ini ayarla. """
        super().on_open()
        self.populate_subjects()
        # RV'nin on_item_selected_callback'ini Python'da atamak daha güvenli
        # Eğer KV'de root.handle_popup_konu_selection şeklinde bir atama yoksa:
        popup_rv = self.ids.get('popup_subjects_rv')
        if popup_rv:
            popup_rv.on_item_selected_callback = self.handle_popup_konu_selection
        else:
            ayat_utils.cprint_debug("HATA: SureSubjectsPopup - popup_subjects_rv ID'si bulunamadı.", "POPUP_KV_ERROR")


    def populate_subjects(self):
        self.subjects_list_data = []
        all_subjects_data_global = ayat_utils.load_subjects_from_db() 

        if all_subjects_data_global and self.target_sure_name:
            # Belirli bir surenin konularını al
            konular_bu_sure_icin = all_subjects_data_global.get("konular_by_sure", {}).get(self.target_sure_name, [])
            
            for konu_data in konular_bu_sure_icin:
                # konu_data yapısı: {'konu': metin, 'baslangic_ayet': int, 'sure_no': int, 'sure_adi_display': str}
                display_text = f"{konu_data.get('baslangic_ayet', '?')}. Ayetten: {konu_data.get('konu', 'Konu bulunamadı.')}"
                self.subjects_list_data.append({
                    'text': display_text,
                    'type': 'popup_konu', # RV için farklı bir tip (isteğe bağlı)
                    'konu_data': konu_data, # Tıklanınca kullanılacak tüm veri
                    'selectable': True
                })
        
        if not self.subjects_list_data:
            self.subjects_list_data.append({'text': f"'{self.target_sure_name}' suresi için konu başlığı bulunamadı.", 'type': 'info', 'selectable': False})
        
        # RecycleView'ı güncelle (eğer ID ile erişiliyorsa)
        popup_rv = self.ids.get('popup_subjects_rv')
        if popup_rv:
            popup_rv.data = self.subjects_list_data
            if popup_rv.layout_manager:
                popup_rv.layout_manager.clear_selection()
            popup_rv.scroll_y = 1


    def handle_popup_konu_selection(self, index, data_item): # rv_instance ve index yerine direkt index ve data_item
        konu_data = data_item.get('konu_data')
        if konu_data and self.read_mode_screen_ref:
            # sure_no zaten self.target_sure_no ile aynı olmalı
            sure_no_konudan = konu_data.get('sure_no')
            ayet_no_konudan = konu_data.get('baslangic_ayet')

            if sure_no_konudan == self.target_sure_no and ayet_no_konudan is not None:
                # ReadModeScreen'i yeni ayete yönlendir
                # Mevcut "Konu Seçimine Dön" bilgisini koruyarak start_reading'i çağır
                self.read_mode_screen_ref.start_reading(
                    sure_no_konudan, 
                    ayet_no_konudan,
                    self.read_mode_screen_ref.return_to_subject_surah_name, # Bu bilgiyi koru
                    self.read_mode_screen_ref.return_to_subject_surah_no    # Bu bilgiyi koru
                )
                self.dismiss() # Popup'ı kapat
            else:
                ayat_utils.cprint_debug(f"HATA: SureSubjectsPopup - Konu verisi geçersiz veya sure no eşleşmiyor. Gelen: {sure_no_konudan}, Beklenen: {self.target_sure_no}", "POPUP_KONU_HATA")

# DÜZELTME: main.py dosyasındaki ilk, daha az detaylı ManageFavoritesPopup sınıfı kaldırıldı.
# Sadece aşağıdaki, daha işlevsel olan sınıf tanımı bırakıldı.
class ManageFavoritesPopup(Popup):
    favorite_management_layout = ObjectProperty(None)
    site_id_to_add_later = StringProperty("")
    app_ref = ObjectProperty(None)
    info_text_for_label = StringProperty('')  # Varsayılanı boş string, bu önemli!

    def __init__(self, **kwargs):
        # app_ref ve site_id_to_add_later gibi özellikler super().__init__ çağrılmadan önce kwargs içinde olmalı
        # ve super().__init__ tarafından atanmalı.
        super().__init__(**kwargs)  # Önce üst sınıfın __init__'ini çağır
        self.update_info_label_text()  # Metni burada hemen güncelle

    def on_open(self):
        super().on_open()
        # Metnin en güncel olduğundan emin olmak için on_open'da tekrar çağrılabilir
        self.update_info_label_text()
        self.populate_current_favorites()

    def update_info_label_text(self):
        if not self.app_ref:
            self.info_text_for_label = "Hata: Uygulama referansı bulunamadı."
            return

        current_favorites_py = self.app_ref.user_settings.get("favorite_translator_ids", [])
        limit_py = self.app_ref.user_settings.get("max_favorites_limit", 3)

        new_text = ""
        if self.site_id_to_add_later and len(current_favorites_py) >= limit_py:
            new_text = "Favori limiti dolu!\nYeni hocayı eklemek için lütfen listeden birini çıkarın:"
        elif not current_favorites_py and not self.site_id_to_add_later:
            new_text = "Henüz favori hocanız yok.\nBu pencereyi kapatıp yıldızla ekleyebilirsiniz."
        else:
            new_text = "Mevcut Favori Hocalarınız:"

        self.info_text_for_label = new_text

    def populate_current_favorites(self):
        self.update_info_label_text()

        if not self.favorite_management_layout or not self.app_ref:
            return

        self.favorite_management_layout.clear_widgets()
        current_favorites = list(self.app_ref.user_settings.get("favorite_translator_ids", []))
        
        if not current_favorites and not self.site_id_to_add_later:
             pass 

        for hoca_site_id in current_favorites:
            hoca_name = "Bilinmeyen Hoca"
            if ayat_utils.hoca_veritabani:
                for name, data in ayat_utils.hoca_veritabani.items():
                    if data.get("site_idler") and hoca_site_id in data["site_idler"]:
                        hoca_name = name
                        break
            
            row = BoxLayout(size_hint_y=None, height=dp(40), spacing=dp(10))
            name_label = Label(text=hoca_name, size_hint_x=0.8, halign='left', valign='middle')
            name_label.bind(width=lambda instance, value: setattr(instance, 'text_size', (value * 0.9, None)))
            row.add_widget(name_label)
            
            remove_button = Button(text="Çıkar", size_hint_x=0.2)
            remove_button.bind(on_press=partial(self.remove_favorite_from_popup_list, hoca_site_id))
            row.add_widget(remove_button)
            self.favorite_management_layout.add_widget(row)

    def remove_favorite_from_popup_list(self, site_id_to_remove, *args):
        if not self.app_ref:
            return
            
        current_favorites = list(self.app_ref.user_settings.get("favorite_translator_ids", [])) 
        if site_id_to_remove in current_favorites:
            current_favorites.remove(site_id_to_remove)
            ayat_utils.cprint_debug(f"{site_id_to_remove} favorilerden popup ile çıkarıldı.", "FAVORITE_POPUP")
            
            if self.site_id_to_add_later and \
                len(current_favorites) < self.app_ref.user_settings.get("max_favorites_limit", 3) and \
                self.site_id_to_add_later not in current_favorites:
                current_favorites.append(self.site_id_to_add_later)
                ayat_utils.cprint_debug(f"{self.site_id_to_add_later} favorilere popup aracılığıyla (yer açılınca) eklendi.", "FAVORITE_POPUP")
                self.site_id_to_add_later = "" # Ekledikten sonra sıfırla
            
            self.app_ref.user_settings["favorite_translator_ids"] = current_favorites
            ayat_utils.save_user_settings(self.app_ref.user_settings)
            self.app_ref.dispatch('on_favorite_hocas_changed')
            
            self.populate_current_favorites()

            if not self.site_id_to_add_later:
                self.dismiss()

class SelectableLabel(RecycleDataViewBehavior, Label):
    index = None
    selected = BooleanProperty(False)
    selectable = BooleanProperty(True)
    item_data = DictProperty(None) # Tıklanan öğenin tüm verisini tutmak için

    _touch_down_time = NumericProperty(0)
    _long_press_scheduled = BooleanProperty(False)
    LONG_PRESS_DURATION = 0.6 # Saniye cinsinden uzun basma süresi

    def refresh_view_attrs(self, rv, index, data):
        self.index = index
        self.item_data = data # Öğenin tüm verisini sakla
        return super(SelectableLabel, self).refresh_view_attrs(rv, index, data)

    def on_touch_down(self, touch):
        if self.collide_point(*touch.pos):
            self._touch_down_time = Clock.get_time()
            self._long_press_scheduled = True
            # Uzun basma kontrolünü zamanla
            Clock.schedule_once(self._check_long_press, self.LONG_PRESS_DURATION)
            # Normal tıklama için de super() çağrısını yapmaya devam et,
            # ancak asıl seçim işlemini on_touch_up'ta kontrol edeceğiz.
            return super(SelectableLabel, self).on_touch_down(touch)
        return False # Eğer dokunma bu widget üzerinde değilse olayı tüketme

    def on_touch_move(self, touch):
        # Eğer parmak çok fazla hareket ederse uzun basmayı iptal et
        if self._long_press_scheduled and not self.collide_point(*touch.pos):
            Clock.unschedule(self._check_long_press)
            self._long_press_scheduled = False
        return super(SelectableLabel, self).on_touch_move(touch)

    def on_touch_up(self, touch):
        if self.collide_point(*touch.pos):
            # Zamanlanmış uzun basma kontrolünü iptal et
            Clock.unschedule(self._check_long_press)
            
            if self._long_press_scheduled: # Eğer uzun basma tetiklenmediyse bu kısa tıklamadır
                self._long_press_scheduled = False # Bayrağı sıfırla
                if self.selectable:
                    # Normal kısa tıklama (seçim) işlemini yap
                    return self.parent.select_with_touch(self.index, touch)
            return super(SelectableLabel, self).on_touch_up(touch)
        return False

    def _check_long_press(self, dt):
        if self._long_press_scheduled: # Hala zamanlanmışsa (yani on_touch_up veya on_touch_move ile iptal edilmediyse)
            self._long_press_scheduled = False # Uzun basma tetiklendi, bayrağı sıfırla
            
            # Uzun basma eylemini gerçekleştir: Popup'ı aç
            app = App.get_running_app()
            if app and hasattr(app.root, 'get_screen'):
                subject_screen = app.root.get_screen('subject_selection')
                if subject_screen:
                    subject_screen.show_full_text_popup_for_item(self.item_data)

    def apply_selection(self, rv, index, is_selected):
        self.selected = is_selected
        if is_selected:
            if hasattr(rv, 'on_item_selected_callback'):
                rv.on_item_selected_callback(index, rv.data[index])

class CustomRecycleBoxLayout(FocusBehavior, LayoutSelectionBehavior, RecycleBoxLayout):
    ''' Custom RecycleBoxLayout for selection handling '''

class FullTextPopup(Popup):
    full_text = StringProperty('')  # Popup'ta gösterilecek tam metin
    popup_title = StringProperty('Konu Detayı')

class SubjectSelectionScreen(Screen):
    subject_rv_data = ListProperty([])
    load_subjects_for_surah_on_enter = StringProperty(None, allownone=True)
    status_label_subjects = ObjectProperty(None)
    current_selection_mode = StringProperty("sure") # 'sure' veya 'konu'
    selected_sure_name_for_subjects = StringProperty("")
    selected_sure_no_for_subjects = NumericProperty(0)
    search_input_subjects = ObjectProperty(None) # KV'den ID'yi bağlamak için
    _original_subject_list_for_current_sure = ListProperty([])
    
    all_subject_data = DictProperty(None) # ayat_utils'den yüklenen tüm veriyi tutar

    def show_full_text_popup_for_item(self, item_data):
        if not item_data:
            return

        full_text_content = "Tam metin bulunamadı."
        popup_title_text = "Konu Detayı"
        
        konu_verisi = item_data.get('konu_data')
        if konu_verisi:
            full_text_content = konu_verisi.get('konu', "İçerik yüklenemedi.")
            sure_adi_display = konu_verisi.get('sure_adi_display')
            if sure_adi_display:
                popup_title_text = f"[{sure_adi_display}] - Konu Detayı"
        else:
            full_text_content = item_data.get('text', "İçerik yüklenemedi.")


        ayat_utils.cprint_debug(f"Popup için tam metin: '{full_text_content[:100]}...'", "POPUP_TEXT")
        
        popup = FullTextPopup(full_text=full_text_content, popup_title=popup_title_text)
        popup.open()

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.all_subject_data = ayat_utils.load_subjects_from_db()
        if not self.all_subject_data or not self.all_subject_data.get("sure_adlari_sirali"):
            self.all_subject_data = {"sure_adlari_sirali": [], "konular_by_sure": {}}
            Clock.schedule_once(lambda dt: self.update_status_message_subjects("Konu listesi veritabanından yüklenemedi!"))

    def on_enter(self, *args):
        super().on_enter(*args)
        
        rv = self.ids.get('subject_recycle_view')
        if rv:
            if not hasattr(rv, 'on_item_selected_callback') or rv.on_item_selected_callback != self.handle_rv_selection:
                rv.on_item_selected_callback = self.handle_rv_selection
            if rv.layout_manager: 
                rv.layout_manager.clear_selection()
        else:
            ayat_utils.cprint_debug("HATA: SubjectSelectionScreen on_enter - subject_recycle_view ID'si bulunamadı.", "SUBJECT_SCREEN_KV")
            self.update_status_message_subjects("Arayüz hatası: Liste görüntülenemiyor.")

        if self.load_subjects_for_surah_on_enter:
            ayat_utils.cprint_debug(f"SubjectScreen on_enter: Okuma modundan '{self.load_subjects_for_surah_on_enter}' suresi için dönüldü, konular yükleniyor.", "SUBJECT_SCREEN_FLOW")
            self.populate_subject_list_for_surah(self.load_subjects_for_surah_on_enter)
            self.load_subjects_for_surah_on_enter = None
        else:
            ayat_utils.cprint_debug(f"SubjectScreen on_enter: Normal giriş, sure listesi gösterilecek.", "SUBJECT_SCREEN_FLOW")
            self.populate_surah_list()


    def update_status_message_subjects(self, message):
        if self.status_label_subjects:
            self.status_label_subjects.text = message
            Clock.schedule_once(lambda dt: setattr(self.status_label_subjects, 'height', self.status_label_subjects.texture_size[1] + dp(10) if self.status_label_subjects.text else 0), 0.1)

    def populate_surah_list(self):
        self.current_selection_mode = "sure"
        self.update_status_message_subjects("Lütfen incelemek istediğiniz bir sure seçiniz veya genel arama yapınız:")
        
        temp_data = []
        if self.all_subject_data and self.all_subject_data.get("sure_adlari_sirali"):
            for sure_adi in self.all_subject_data["sure_adlari_sirali"]:
                temp_data.append({'text': sure_adi, 'type': 'sure', 'sure_adi_data': sure_adi, 'selectable': True})
        else:
            self.update_status_message_subjects("Gösterilecek sure bulunamadı.")
        
        rv = self.ids.get('subject_recycle_view')
        if rv:
            rv.data = temp_data
            if rv.layout_manager:
                rv.layout_manager.clear_selection()
            rv.scroll_y = 1
        
        header_label = self.ids.get('subjects_header_label')
        if header_label: header_label.text = "Sureler"
        
        search_input = self.ids.get('search_input_subjects_id')
        if search_input:
            search_input.disabled = False
            search_input.hint_text = "Sure adı veya genel konu ara..."

        back_button = self.ids.get('subjects_back_button')
        if back_button: back_button.disabled = True


    def filter_displayed_subjects(self, search_text):
        search_text_normalized = ayat_utils.normalize_turkish_text_for_search(search_text.strip())
        
        rv = self.ids.get('subject_recycle_view')
        header_label = self.ids.get('subjects_header_label')
        back_button = self.ids.get('subjects_back_button')

        if not search_text_normalized:
            if self.current_selection_mode == "konu":
                self.populate_subject_list_for_surah(self.selected_sure_name_for_subjects)
            else: 
                self.populate_surah_list()
            if rv and rv.layout_manager: rv.layout_manager.clear_selection()
            if rv: rv.scroll_y = 1
            return

        filtered_results_for_rv = []
        
        found_sures = []
        all_surahs_from_db = ayat_utils.get_all_surahs_with_aliases_db()
        if all_surahs_from_db:
            for surah_entry in all_surahs_from_db:
                official_name = surah_entry['name']
                aliases = surah_entry['aliases']
                
                texts_to_check = [official_name] + aliases
                found_in_this_sure_name = False
                for text_to_check in texts_to_check:
                    normalized_text_to_check = ayat_utils.normalize_turkish_text_for_search(text_to_check)
                    if search_text_normalized in normalized_text_to_check:
                        found_in_this_sure_name = True
                        break
                
                if found_in_this_sure_name:
                    if official_name in self.all_subject_data.get("sure_adlari_sirali", []):
                         found_sures.append({
                            'text': f"SURE: {official_name}", 
                            'type': 'sure', 
                            'sure_adi_data': official_name,
                            'selectable': True
                        })
        
        found_konular = []
        if self.all_subject_data and self.all_subject_data.get("konular_by_sure"):
            for sure_adi_iter, konular_listesi_iter in self.all_subject_data["konular_by_sure"].items():
                for konu_data_iter in konular_listesi_iter:
                    konu_metni_iter = konu_data_iter.get('konu', '')
                    konu_metni_normalized_iter = ayat_utils.normalize_turkish_text_for_search(konu_metni_iter)
                    
                    if search_text_normalized in konu_metni_normalized_iter:
                        display_text = f"KONU ({konu_data_iter.get('sure_adi_display', sure_adi_iter)} - Ayet {konu_data_iter.get('baslangic_ayet', '?')}): {konu_metni_iter}"
                        found_konular.append({
                            'text': display_text,
                            'type': 'global_konu_sonucu',
                            'konu_data': konu_data_iter,
                            'selectable': True
                        })

        filtered_results_for_rv.extend(found_sures)
        filtered_results_for_rv.extend(found_konular)
        
        self.subject_rv_data = filtered_results_for_rv
        self.current_selection_mode = "global_search_results"

        if rv:
            rv.data = self.subject_rv_data
            if rv.layout_manager:
                rv.layout_manager.clear_selection()
            rv.scroll_y = 1
        
        if not filtered_results_for_rv:
            self.update_status_message_subjects(f"'{search_text}' için sure veya konu bulunamadı.")
            if header_label: header_label.text = "Arama Sonucu Yok"
        else:
            self.update_status_message_subjects(f"Arama Sonuçları ({len(filtered_results_for_rv)} öğe):")
            if header_label: header_label.text = "Genel Arama Sonuçları"
        
        if back_button:
            back_button.disabled = False

    def populate_subject_list_for_surah(self, sure_adi_secilen):
        self.current_selection_mode = "konu"
        self.selected_sure_name_for_subjects = sure_adi_secilen
        
        sure_no = ayat_utils.get_sure_no_from_name_db(sure_adi_secilen)
        
        if sure_no is None:
            self.update_status_message_subjects(f"'{sure_adi_secilen}' suresi için numara bulunamadı. Lütfen geri dönüp tekrar deneyin.")
            ayat_utils.cprint_debug(f"HATA: populate_subject_list_for_surah - '{sure_adi_secilen}' için sure no bulunamadı.", "SUBJECT_SCREEN_ERROR")
            self._original_subject_list_for_current_sure = [] 
            self.subject_rv_data = []
            rv_check = self.ids.get('subject_recycle_view')
            if rv_check: rv_check.data = []
            return

        self.selected_sure_no_for_subjects = sure_no
        self.update_status_message_subjects(f"'{sure_adi_secilen}' Suresi Konuları (Okumak için bir konuya tıklayın):")
        
        temp_data = []
        self._original_subject_list_for_current_sure = [] 

        konular_veritabani = self.all_subject_data.get("konular_by_sure", {}).get(sure_adi_secilen, [])
        if konular_veritabani:
            for konu_data in konular_veritabani:
                display_text = f"{konu_data['baslangic_ayet']}. Ayetten itibaren: {konu_data['konu']}"
                item_for_list = {
                    'text': display_text, 
                    'type': 'konu', 
                    'konu_data': konu_data,
                    'selectable': True
                }
                temp_data.append(item_for_list)
                self._original_subject_list_for_current_sure.append(item_for_list) 
        
        self.subject_rv_data = list(temp_data)

        if not self.subject_rv_data:
            self.update_status_message_subjects(f"'{sure_adi_secilen}' suresi için konu bulunamadı.")

        rv = self.ids.get('subject_recycle_view')
        if rv:
            rv.data = self.subject_rv_data
            if rv.layout_manager:
                rv.layout_manager.clear_selection()
            rv.scroll_y = 1

        search_input = self.ids.get('search_input_subjects_id')
        if search_input:
            search_input.text = "" 
            search_input.disabled = True # DÜZELTME: Konu listesindeyken arama devre dışı
            search_input.hint_text = f"'{sure_adi_secilen}' konuları listeleniyor"
        
        header_label = self.ids.get('subjects_header_label')
        if header_label: header_label.text = f"{sure_adi_secilen} Suresi Konuları"
        
        back_button = self.ids.get('subjects_back_button')
        if back_button: back_button.disabled = False


    def handle_rv_selection(self, index, data):
        item_type = data.get('type')
        ayat_utils.cprint_debug(f"RV Seçimi: Tip='{item_type}', Veri='{data.get('text','')[:50]}...'", "RV_SELECTION")

        if item_type == 'sure':
            sure_adi_data_attr = data.get('sure_adi_data')
            if sure_adi_data_attr:
                search_input = self.ids.get('search_input_subjects_id')
                if search_input: search_input.text = ""
                self.populate_subject_list_for_surah(sure_adi_data_attr)
        
        elif item_type == 'konu' or item_type == 'global_konu_sonucu':
            konu_data_attr = data.get('konu_data')
            if konu_data_attr:
                sure_no_from_konu = konu_data_attr.get('sure_no')
                baslangic_ayet_from_konu = konu_data_attr.get('baslangic_ayet')
                sure_adi_display_from_konu = konu_data_attr.get('sure_adi_display') 

                if sure_no_from_konu is not None and baslangic_ayet_from_konu is not None and sure_adi_display_from_konu:
                    self.update_status_message_subjects(f"Okuma moduna yönlendiriliyorsunuz: {sure_adi_display_from_konu}, {baslangic_ayet_from_konu}. ayetten...")
                    
                    if item_type == 'global_konu_sonucu':
                        self.selected_sure_name_for_subjects = sure_adi_display_from_konu 
                        self.selected_sure_no_for_subjects = sure_no_from_konu
                    
                    Clock.schedule_once(lambda dt, sn=sure_no_from_konu, an=baslangic_ayet_from_konu: self.go_to_read_mode_with_subject(sn, an), 0.3)
                else:
                    ayat_utils.cprint_debug(f"HATA: RV Konu seçimi - sure_no veya baslangic_ayet eksik: {konu_data_attr}", "RV_SELECTION_ERROR")
                    self.update_status_message_subjects("Hata: Ayet bilgileri eksik, okuma modu başlatılamıyor.")
            else:
                ayat_utils.cprint_debug(f"HATA: RV Konu seçimi - konu_data eksik: {data}", "RV_SELECTION_ERROR")


    def go_to_read_mode_with_subject(self, sure_no, ayet_no):
        app = App.get_running_app()
        if app and app.root and hasattr(app.root, 'get_screen'):
            read_mode_screen = app.root.get_screen('read_mode')
            if read_mode_screen:
                if self.selected_sure_name_for_subjects and self.selected_sure_no_for_subjects != 0:
                    ayat_utils.cprint_debug(f"Okuma Moduna Geçiliyor: Sure {sure_no}, Ayet {ayet_no}. Geri dönüş için: {self.selected_sure_name_for_subjects} (No: {self.selected_sure_no_for_subjects})", "SUBJECT_NAV")
                    read_mode_screen.start_reading(sure_no, ayet_no, 
                                                   came_from_subjects_surah_name=self.selected_sure_name_for_subjects,
                                                   came_from_subjects_surah_no=self.selected_sure_no_for_subjects)
                    app.root.current = 'read_mode'
                    if hasattr(app.root, 'transition'): app.root.transition = FadeTransition(duration=0.3)
                else:
                    self.update_status_message_subjects("Hata: Geri dönüş için sure bilgisi eksik.")
                    ayat_utils.cprint_debug(f"HATA: go_to_read_mode_with_subject - selected_sure_name_for_subjects veya selected_sure_no_for_subjects eksik/hatalı.", "SUBJECT_NAV_ERROR")
            else:
                self.update_status_message_subjects("Hata: Okuma modu ekranı bulunamadı.")
        else:
            self.update_status_message_subjects("Hata: Uygulama yapısı uygun değil.")
            
    def go_back_to_surah_list(self):
        search_input = self.ids.get('search_input_subjects_id')
        if search_input:
            search_input.text = ""
        self.populate_surah_list()

    def go_to_main_menu_from_subjects(self):
        app = App.get_running_app()
        if app and app.root:
            app.root.current = 'main'
            if hasattr(app.root, 'transition'): app.root.transition = FadeTransition(duration=0.2)

class ReadModeStartPopup(Popup):
    main_screen_ref = ObjectProperty(None)
    start_sure_no = NumericProperty(1)
    start_ayet_no = NumericProperty(1)

    def __init__(self, main_screen_ref, current_sure_no=None, current_ayet_no=None, **kwargs):
        super().__init__(**kwargs)
        self.main_screen_ref = main_screen_ref
        
        option2_button = self.ids.get('option2_button')
        if option2_button: 
            if current_sure_no and current_ayet_no:
                s_name = ayat_utils.get_sure_name_db(int(current_sure_no)) or str(current_sure_no)
                option2_button.text = f"Mevcut Ayetten Başla ({s_name} - {current_ayet_no})"
                self.start_sure_no = int(current_sure_no)
                self.start_ayet_no = int(current_ayet_no)
                option2_button.disabled = False
            else:
                option2_button.text = "Mevcut Ayetten Başla (Ayarlanmadı)"
                option2_button.disabled = True
        else:
            ayat_utils.cprint_debug("UYARI: ReadModeStartPopup - 'option2_button' ID'si bulunamadı.", "POPUP_INIT")

    def start_from_fatiha(self):
        if self.main_screen_ref:
            self.main_screen_ref.go_to_read_mode(1, 1)
        self.dismiss()

    def start_from_current(self):
        option2_button = self.ids.get('option2_button')
        if option2_button and not option2_button.disabled:
            if self.main_screen_ref:
                    self.main_screen_ref.go_to_read_mode(self.start_sure_no, self.start_ayet_no)
        self.dismiss()

    def start_from_custom(self): 
        custom_input_widget = self.ids.get('custom_sorgu_input')
        if not custom_input_widget:
            ayat_utils.cprint_debug("HATA: ReadModeStartPopup - 'custom_sorgu_input' bulunamadı", "POPUP_ERROR")
            self.dismiss()
            return

        sorgu = custom_input_widget.text.strip()
        original_hint = "Veya buradan girin (Örn: Bakara 5)" 
        if sorgu:
            sure_no, ayet_no_list, is_range = ayat_utils.parse_sure_ayet_input(sorgu)
            if sure_no and ayet_no_list and not is_range:
                ayet_no = ayet_no_list[0]
                if self.main_screen_ref:
                    self.main_screen_ref.go_to_read_mode(sure_no, ayet_no)
                self.dismiss()
            else: 
                custom_input_widget.hint_text = "Geçersiz! Örn: Bakara 5"
                custom_input_widget.text = ""
                Clock.schedule_once(lambda dt: setattr(custom_input_widget, 'hint_text', original_hint), 2)
        else: 
            custom_input_widget.hint_text = "Lütfen giriş yapın!"
            Clock.schedule_once(lambda dt: setattr(custom_input_widget, 'hint_text', original_hint), 2)

class AIScreen(Screen):
    context_data = DictProperty(None) # Ayet bağlamını tutacak property

    def on_enter(self, *args):
        """Ekran açıldığında bağlam bilgisini ve butonları ayarlar."""
        super().on_enter(*args)
        context_label = self.ids.get('context_info_label')
        remove_button = self.ids.get('remove_context_button')
        if not context_label or not remove_button: return
        
        if self.context_data:
            sure_adi = self.context_data.get('sure_adi', '')
            ayet_no = self.context_data.get('ayet_no', '')
            context_label.text = f"Soru, [{sure_adi} Suresi, {ayet_no}. Ayet] bağlamında sorulacaktır."
            context_label.opacity = 1
            remove_button.opacity = 1
            remove_button.disabled = False
        else:
            context_label.text = "Genel bir soru sorulacak (ayet bağlamı yok)."
            context_label.opacity = 0.7
            remove_button.opacity = 0
            remove_button.disabled = True

    def clear_context(self):
        """Ayet bağlamını temizler ve arayüzü günceller."""
        self.context_data = {}
        self.on_enter()

    def send_to_ai(self):
        if platform != 'android':
            popup = Popup(title='Uyarı',
                          content=Label(text='Bu özellik sadece Android cihazlarda çalışır.'),
                          size_hint=(0.8, 0.4))
            popup.open()
            return

        from jnius import autoclass
        Intent = autoclass('android.content.Intent')
        String = autoclass('java.lang.String')
        PythonActivity = autoclass('org.kivy.android.PythonActivity')

        user_prompt = self.ids.ai_text_input.text
        if not user_prompt.strip():
            self.ids.ai_status_label.text = "Lütfen önce bir soru veya istek girin."
            return
        
        system_prompt = (
            "Sen, soruları Kur'an ışığında, Ehl-i Sünnet perspektifinden, "
            "tarafsız, saygılı ve akademik bir dille yanıtlayan bir İslam alimisin. "
            "Cevaplarını ayet kaynaklarıyla desteklemeye özen göster. "
            "Cevaplarının bir yapay zekadan çıktığını ve islami konularda referans alınamayacağını mutlaka belirt. "
            "Modern fıkhi meselelerde ihtiyatlı ve dengeli bir yaklaşım sergile."
        )

        context_header = ""
        if self.context_data:
            sure_adi = self.context_data.get('sure_adi', 'Bilinmiyor')
            ayet_no = self.context_data.get('ayet_no', 'Bilinmiyor')
            arapca = self.context_data.get('arapca_metin', 'Mevcut değil')
            
            # --- YENİ AKILLI MEAL SEÇİMİ MANTIĞI ---
            mealler = self.context_data.get('mealler', [])
            selected_meals_for_ai = []
            
            app = App.get_running_app()
            if app and mealler:
                favorite_ids = app.user_settings.get("favorite_translator_ids", [])
                
                # 1. Öncelik: Favori hocaların meallerini bul
                for meal in mealler:
                    if meal.get('id') in favorite_ids:
                        selected_meals_for_ai.append(meal)
                
                # 2. Öncelik: Eğer hiç favori bulunamadıysa, varsayılan hocalarınkini al
                if not selected_meals_for_ai:
                    for hoca_id in DEFAULT_READ_MODE_HOCA_IDS:
                        for meal in mealler:
                            if meal.get('id') == hoca_id:
                                selected_meals_for_ai.append(meal)
                                break # Aynı hocadan birden fazla olmasın
            
            meal_metinleri = []
            if selected_meals_for_ai:
                for meal in selected_meals_for_ai:
                    yazar = meal.get('yazar_raw', 'Bilinmiyor')
                    metin = meal.get('metin', '')
                    meal_metinleri.append(f"- {yazar}: \"{metin}\"")

            formatted_mealler = '\n'.join(meal_metinleri)
            
            context_header = (
                f"BAĞLAM BİLGİSİ:\n"
                f"Kullanıcı şu an [{sure_adi} Suresi, {ayet_no}. Ayet] üzerine düşünmektedir.\n"
                f"Ayetin Arapça Metni: {arapca}\n"
                f"Ayetin Bazı Mealleri:\n"
                f"{formatted_mealler}\n\n"
            )

        full_prompt = (
            f"SİSTEM TALİMATI:\n{system_prompt}\n\n"
            f"{context_header}"
            f"KULLANICININ SORUSU:\n{user_prompt}"
        )

        intent = Intent()
        intent.setAction(Intent.ACTION_SEND)
        intent.putExtra(Intent.EXTRA_TEXT, String(full_prompt))
        intent.setType("text/plain")
        chooser = Intent.createChooser(intent, String("Bir Yapay Zeka Uygulaması Seçin"))
        PythonActivity.mActivity.startActivity(chooser)
        self.ids.ai_status_label.text = "İsteğiniz diğer uygulamalara yönlendiriliyor..."

class MainScreen(Screen):
    sorgu_input = ObjectProperty(None)
    result_label = ObjectProperty(None)
    arabic_label = ObjectProperty(None) 
    transliteration_label = ObjectProperty(None) 
    mealler_layout = ObjectProperty(None)
    favorite_ayet_button = ObjectProperty(None)

    word_analysis_mode = BooleanProperty(False)
    current_ayet_data = DictProperty({})
    hoca_search_input_main = ObjectProperty(None)
    _original_mealler_data_main = ListProperty([])
    current_sure_no_for_read_mode = NumericProperty(0) 
    current_ayet_no_for_read_mode = NumericProperty(0) 
    _current_hoca_info_popup = ObjectProperty(None, allownone=True)
    _word_info_popup = ObjectProperty(None, allownone=True)
    _event_bound_fav_hocas = BooleanProperty(False) 
    _event_bound_fav_ayets = BooleanProperty(False)

    def go_to_ai_screen_with_context(self):
        """AI ekranına geçmeden önce mevcut ayet bağlamını aktarır."""
        app = App.get_running_app()
        if not app: return
        
        ai_screen = app.root.get_screen('ai_screen')
        
        # Eğer ekranda bir ayet görüntüleniyorsa, onun verisini aktar
        if self.current_ayet_data:
            ai_screen.context_data = self.current_ayet_data
        else:
            ai_screen.context_data = {} # Bağlam yoksa boş gönder
            
        app.root.current = 'ai_screen'

    def _dummy_ref_press_main(self, instance, ref_value):
        pass

    def _filter_displayed_mealler(self, search_text=""):
        if not self.mealler_layout:
            self.update_status_console("HATA: _filter_displayed_mealler - mealler_layout bulunamadı.")
            return
        self.mealler_layout.clear_widgets()

        normalized_search_text = ayat_utils.normalize_turkish_text_for_search(search_text)
        displayed_meal_count = 0
        app = App.get_running_app()

        # --- YENİ SIRALAMA MANTIĞI BAŞLANGICI ---
        
        # Orijinal meal listesi üzerinde işlem yapacağız
        original_mealler = self._original_mealler_data_main
        
        if not original_mealler:
            if not normalized_search_text:
                no_meal_label = Label(text="Bu ayet için meal verisi bulunamadı.", size_hint_y=None, height=dp(30))
                self.mealler_layout.add_widget(no_meal_label)
            return

        # Favori hoca ID'lerini al
        favorite_ids = app.user_settings.get("favorite_translator_ids", []) if app else []
        
        sorted_mealler = []
        favori_mealler = []
        diger_mealler = []

        # Mealleri favori olanlar ve olmayanlar olarak iki listeye ayır
        for meal in original_mealler:
            meal_id = meal.get('id')
            if meal_id in favorite_ids:
                favori_mealler.append(meal)
            else:
                diger_mealler.append(meal)
        
        # Son listeyi önce favorileri, sonra diğerlerini ekleyerek oluştur
        sorted_mealler.extend(favori_mealler)
        sorted_mealler.extend(diger_mealler)

        # --- YENİ SIRALAMA MANTIĞI SONU ---


        # Artık ekrana çizim yaparken sıralanmış listeyi kullanacağız
        for meal_data in sorted_mealler:
            hoca_adi_raw = meal_data.get('yazar_raw', 'Bilinmeyen Yazar')
            site_id = meal_data.get('id')
            canonical_tam_ad = ayat_utils.site_id_to_hoca_tam_ad_haritasi.get(site_id.casefold()) if site_id else None
            goruntulenecek_ad = canonical_tam_ad if canonical_tam_ad and ayat_utils.hoca_veritabani.get(canonical_tam_ad) else hoca_adi_raw
            
            add_this_meal = False
            if not normalized_search_text:
                add_this_meal = True
            else:
                normalized_hoca_adi = ayat_utils.normalize_turkish_text_for_search(goruntulenecek_ad)
                if normalized_search_text in normalized_hoca_adi:
                    add_this_meal = True
            
            if add_this_meal:
                meal_entry_layout = BoxLayout(orientation='vertical', size_hint_y=None, spacing=dp(5))
                meal_entry_layout.bind(minimum_height=meal_entry_layout.setter('height'))
                
                hoca_header_layout = BoxLayout(orientation='horizontal', size_hint_y=None, height=dp(40), spacing=dp(5))
                is_fav_hoca = False 
                if site_id and app: is_fav_hoca = app.is_hoca_favorite(site_id)
                
                star_button = ToggleButton(
                    background_normal='images/star_empty.png', background_down='images/star_filled.png',
                    size_hint_x=None, width=dp(36), size_hint_y=None, height=dp(36),
                    state='down' if is_fav_hoca else 'normal', border=(0,0,0,0)
                )
                if site_id and app: 
                    star_button.bind(on_press=partial(app.toggle_hoca_favorite, site_id, star_button))
                else: 
                    star_button.disabled = True
                
                hoca_name_label = Label(
                    text=f"{goruntulenecek_ad} (ID: {site_id or 'N/A'})", 
                    size_hint_x=1, halign='left', valign='middle', font_size=dp(14)
                )
                hoca_name_label.bind(text_size=lambda i,v: setattr(i,'text_size',(i.width - dp(10),None)))
                hoca_name_label.bind(on_touch_down=partial(self.trigger_hoca_info_popup_from_label, goruntulenecek_ad, canonical_tam_ad, site_id))
                
                hoca_header_layout.add_widget(star_button)
                hoca_header_layout.add_widget(hoca_name_label)
                
                meal_metni = meal_data.get('metin', 'Meal bulunamadı.')
                meal_text_input = TextInput(
                    text=meal_metni, readonly=True, multiline=True, size_hint_y=None,
                    background_color=(0.95,0.95,0.95,1), foreground_color=(0,0,0,1),
                    font_size=dp(15)
                )
                meal_text_input.bind(minimum_height=meal_text_input.setter('height'))
                
                meal_entry_layout.add_widget(hoca_header_layout)
                meal_entry_layout.add_widget(meal_text_input)
                
                self.mealler_layout.add_widget(meal_entry_layout)
                displayed_meal_count += 1
        
        if displayed_meal_count == 0:
            if normalized_search_text:
                message_text = f"'{search_text}' ile eşleşen hoca/meal bulunamadı."
            elif not self._original_mealler_data_main:
                message_text = "Bu ayet için meal verisi bulunamadı."
            else:
                message_text = "Mealler yüklenirken bir sorun oluştu."

            no_content_label = Label(text=message_text, size_hint_y=None, height=dp(30))
            self.mealler_layout.add_widget(no_content_label)

        if not normalized_search_text and self._original_mealler_data_main:
            scroll_view = self.ids.get('main_screen_scroll_view')
            target_widget = self.ids.get('hoca_search_input_wrapper') 

            if scroll_view and target_widget:
                Clock.schedule_once(lambda dt: scroll_view.scroll_to(target_widget, padding=dp(10), animate=False), 0.1)
            elif scroll_view:
                Clock.schedule_once(lambda dt: setattr(scroll_view, 'scroll_y', 1), 0.1)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        Clock.schedule_once(self._late_init)

    def add_to_history(self, sure_no, ayet_no, data):
        if not data or data.get("error"):
            self.update_status_console(f"UYARI: add_to_history - Hatalı veya eksik veri, geçmişe eklenmiyor.")
            return

        ayah_db_id = data.get('ayah_db_id')

        if not ayah_db_id:
            self.update_status_console(f"UYARI: add_to_history - Veride 'ayah_db_id' bulunamadı. S:{sure_no} A:{ayet_no}. Geçmişe eklenmiyor.")
            return

        try:
            if ayat_utils.add_query_to_history_db(int(ayah_db_id)):
                ayat_utils.load_query_history()
            else:
                self.update_status_console(f"HATA: Ayet (ayah_db_id: {ayah_db_id}) SorguGecmisi tablosuna eklenirken sorun oluştu.")

        except (ValueError, Exception) as e:
            self.update_status_console(f"HATA: add_to_history içinde hata oluştu: {e}")
            traceback.print_exc()

    def go_to_bookmark(self):
        """Kaydedilmiş yer işaretini yükler ve okuma moduna geçer."""
        sure_no, ayet_no = ayat_utils.load_last_read_location()
        if sure_no and ayet_no:
            self.go_to_read_mode(sure_no, ayet_no)
        else:
            if self.result_label:
                self.result_label.text = "Daha önce bir yer işareti kaydetmediniz."

    def _late_init(self, dt):
        app = App.get_running_app()
        if app:
            if not self._event_bound_fav_hocas:
                try:
                    app.bind(on_favorite_hocas_changed=self.refresh_mealler_if_needed)
                    self._event_bound_fav_hocas = True
                except Exception as e:
                    ayat_utils.cprint_debug(f"HATA: MainScreen on_favorite_hocas_changed bağlanamadı: {e}", "EVENT_BIND_ERROR")
            
            if not self._event_bound_fav_ayets:
                try:
                    app.bind(on_favorite_ayets_changed=self.update_favorite_ayet_button_status)
                    self._event_bound_fav_ayets = True
                except Exception as e:
                    ayat_utils.cprint_debug(f"HATA: MainScreen on_favorite_ayets_changed bağlanamadı: {e}", "EVENT_BIND_ERROR")

    def go_to_subject_selection(self):
        app = App.get_running_app()
        if app and app.root:
            # Konu ekranına gitmeden önce, oradan geri dönüldüğünde belirli bir sureyi gösterme bayrağını temizle
            subject_screen = app.root.get_screen('subject_selection')
            subject_screen.load_subjects_for_surah_on_enter = None
            
            app.root.current = 'subject_selection'
            if hasattr(app.root, 'transition'): app.root.transition = FadeTransition(duration=0.2)
        else:
            self.update_status_console("HATA: Konu seçme ekranına gidilemedi.")

    def refresh_mealler_if_needed(self, *args):
        if self.current_ayet_data and self.current_ayet_data.get('sure_no'):
            self.update_status_console("Favori hocalar değişti, MainScreen mealleri yenileniyor.")
            self.display_ayet_details(dict(self.current_ayet_data),
                                      self.current_ayet_data.get('_context_message_internal', ''))
        else:
            self.update_status_console("Favori hocalar değişti, ancak MainScreen'de yenilenecek mevcut ayet yok.")

    def get_ayet_button_pressed(self):
        self.update_status_console("Ayet getirme isteği alındı (Buton)...")
        sorgu_metni = ""
        if self.sorgu_input:
            sorgu_metni = self.sorgu_input.text.strip()
        
        if not sorgu_metni:
            if self.result_label: self.result_label.text = "Lütfen Sure ve Ayet Numarası giriniz. (Örn: Bakara 5)"
            self.update_status_console("HATA: Sure/Ayet Numarası girilmedi.")
            return

        try:
            sure_no, ayet_no_list, is_range = ayat_utils.parse_sure_ayet_input(sorgu_metni)
            
            if sure_no is None or not ayet_no_list:
                if self.result_label: self.result_label.text = f"'{sorgu_metni}' girdisi geçersiz. Örnek: Bakara 5"
                return

            if is_range or len(ayet_no_list) > 1:
                # Aralık veya çoklu ayet durumunda okuma moduna yönlendirelim
                self.go_to_read_mode(sure_no, ayet_no_list[0])
                return 
            else:
                ayet_no_to_fetch = ayet_no_list[0]
            
            self.fetch_ayet_data(sure_no, ayet_no_to_fetch, context_message="(Girişten)")
            
        except Exception as e:
            if self.result_label: self.result_label.text = f"Ayet getirilirken bir hata oluştu: {e}"
            self.update_status_console(f"HATA: Ayet getirme sırasında genel hata: {e}")
            traceback.print_exc()

    def fetch_ayet_data(self, sure_no, ayet_no, force_refresh=False, context_message=""):
        sure_adi_temp = ayat_utils.get_sure_name_db(sure_no)
        if not sure_adi_temp:
            self.update_status_console(f"HATA: {sure_no} numaralı sure için ad alınamadı.")
            self.set_error_message_on_header(f"Hata: {sure_no} numaralı sure bulunamadı.")
            return

        status_msg = f"{sure_adi_temp} {ayet_no} getiriliyor..."
        self.update_status_console(status_msg)
        if self.result_label:
            self.result_label.text = status_msg
        self.clear_display_except_header()

        def _fetch_data_on_thread():
            fetched_data = ayat_utils.get_complete_ayah_details_from_db(sure_no, ayet_no)

            if fetched_data and fetched_data.get("error") is None:
                self.current_sure_no_for_read_mode = sure_no
                self.current_ayet_no_for_read_mode = ayet_no
                self.add_to_history(sure_no, ayet_no, fetched_data)
                Clock.schedule_once(lambda dt: self.display_ayet_details(fetched_data, context_message))
            else:
                self.current_sure_no_for_read_mode = 0
                self.current_ayet_no_for_read_mode = 0
                error_msg_detail = fetched_data.get("error", "Bilinmeyen hata.") if fetched_data else "Veri alınamadı."
                final_error_msg = f"{sure_adi_temp} {ayet_no} için veri alınamadı. ({error_msg_detail})"
                Clock.schedule_once(lambda dt: self.set_error_message_on_header(final_error_msg))

        threading.Thread(target=_fetch_data_on_thread, daemon=True).start()

    def display_ayet_details(self, ayet_verisi_full, context_message=""):
        self.current_ayet_data = dict(ayet_verisi_full) 
        self.current_ayet_data['_context_message_internal'] = context_message
        
        if self.arabic_label: self.arabic_label.text = ""
        if self.transliteration_label: self.transliteration_label.text = ""
        
        if self.current_ayet_data and self.current_ayet_data.get("sure_adi") and self.current_ayet_data.get("sure_adi") != "Bulunamadı":
            s_adi = self.current_ayet_data.get('sure_adi', '')
            a_str = self.current_ayet_data.get('ayet_numarasi_str', f"{self.current_ayet_data.get('ayet_no', '')}. Ayet")
            if self.result_label: 
                self.result_label.text = f"📖 {s_adi} - {a_str} {context_message} 📖"
            
            self.update_favorite_ayet_button_status()

            if self.arabic_label:
                # Arapça metin etiketi artık statik bir mesaj gösterecek
                self.arabic_label.text = "Şu an için ayetin arapça metnini görüntüleyemiyoruz ama isterseniz 'Arapçayı Kopyala' butonundan metni kopyalayıp görüntüleyebilirsiniz."
                self.arabic_label.markup = False # Markup kullanmıyoruz
                self.arabic_label.base_direction = None # Yönlendirme normal
                self.arabic_label.text_language = None # Dil normal
                self.arabic_label.halign = 'center' # Ortala
                self.arabic_label.valign = 'middle'

                def update_label_size(label_widget, width):
                    if label_widget and label_widget.text:
                        label_widget.text_size = (width, None)
                        label_widget.height = label_widget.texture_size[1] + dp(15)
                    elif label_widget:
                        label_widget.height = 0
                
                Clock.schedule_once(lambda dt: update_label_size(self.arabic_label, self.arabic_label.width), 0.01)

            trans_data_ayet = self.current_ayet_data.get('transliterasyon', {})
            if self.transliteration_label:
                if trans_data_ayet and trans_data_ayet.get('metin'):
                    self.transliteration_label.text = f"Transliterasyon:\n{trans_data_ayet.get('metin')}"
                    Clock.schedule_once(lambda dt: update_label_size(self.transliteration_label, self.transliteration_label.width), 0.01)
                else:
                    self.transliteration_label.text = ""
                    self.transliteration_label.height = 0
            
            self._original_mealler_data_main = list(self.current_ayet_data.get('mealler', [])) 
            search_input = self.ids.get('hoca_search_input_main')
            current_search_text = search_input.text if search_input else ""
            self._filter_displayed_mealler(current_search_text)
        else:
            error_msg = "Ayet detayları görüntülenemedi."
            if ayet_verisi_full and "error" in ayet_verisi_full:
                error_msg += f" (Detay: {ayet_verisi_full['error']})"
            self.set_error_message_on_header(error_msg) 
            self.clear_display_except_header(keep_header_message=True) 
            self.current_ayet_data = {} 
            self._original_mealler_data_main = [] 
            if self.favorite_ayet_button: 
                self.favorite_ayet_button.disabled = True
                self.favorite_ayet_button.state = 'normal'
            search_input_hata = self.ids.get('hoca_search_input_main')
            if search_input_hata:
                search_input_hata.text = ""
    
    def update_favorite_ayet_button_status(self, *args):
        app = App.get_running_app()
        if not self.favorite_ayet_button: return

        if self.current_ayet_data and app:
            sure_no = self.current_ayet_data.get('sure_no')
            ayet_no = self.current_ayet_data.get('ayet_no')

            if sure_no is not None and ayet_no is not None:
                is_fav = app.is_ayet_favorite(sure_no, ayet_no)
                self.favorite_ayet_button.state = 'down' if is_fav else 'normal'
                self.favorite_ayet_button.disabled = False
            else:
                self.favorite_ayet_button.disabled = True
                self.favorite_ayet_button.state = 'normal'
        else:
            self.favorite_ayet_button.disabled = True
            self.favorite_ayet_button.state = 'normal'

    def get_random_ayet_button_pressed(self): 
        self.update_status_console("Rastgele ayet getiriliyor...")
        if self.result_label:
            self.result_label.text = "Rastgele ayet getiriliyor..."
        
        sure_no, ayet_no = ayat_utils.get_random_ayah_info()
        if sure_no and ayet_no:
            sure_adi = ayat_utils.get_sure_name_db(sure_no) or str(sure_no)
            if self.sorgu_input:
                self.sorgu_input.text = f"{sure_adi} {ayet_no}" 
            
            self.fetch_ayet_data(sure_no, ayet_no, context_message="(Rastgele)")
        else:
            msg = "Rastgele ayet seçilemedi. Veritabanı kontrol edilebilir."
            self.update_status_console(msg)
            if self.result_label:
                self.result_label.text = msg
    
    def trigger_hoca_info_popup_from_label(self, goruntulenecek_ad, canonical_tam_ad, site_id, label_instance, touch):
        if label_instance.collide_point(*touch.pos):
            self.show_hoca_info_popup(goruntulenecek_ad, canonical_tam_ad, site_id)
            return True
        return False

    def show_hoca_info_popup(self, goruntulenecek_ad, canonical_tam_ad, site_id_from_meal, *args):
        app = App.get_running_app()
        hoca_adi_sorgu = canonical_tam_ad if canonical_tam_ad is not None else goruntulenecek_ad
        hoca_data = ayat_utils.get_hoca_bilgisi_data(hoca_adi_sorgu)
        
        popup_content_main = BoxLayout(orientation='vertical', padding=dp(10), spacing=dp(10))
        title_star_layout = BoxLayout(orientation='horizontal', size_hint_y=None, height=dp(40))
        popup_title_text = f"{hoca_data.get('tam_ad', goruntulenecek_ad)}" if hoca_data else goruntulenecek_ad
        title_label = Label(text=popup_title_text, size_hint_x=0.80, bold=True, font_size=dp(16), halign='left', valign='middle')
        title_label.bind(text_size=lambda i,v: setattr(i,'text_size',(i.width,None)))
        title_star_layout.add_widget(title_label)
        
        if site_id_from_meal and app:
            is_fav = app.is_hoca_favorite(site_id_from_meal)
            star_button_popup = ToggleButton(
                background_normal=STAR_EMPTY_IMG, background_down=STAR_FILLED_IMG,
                size_hint_x=None, width=dp(36), size_hint_y=None, height=dp(36),
                state='down' if is_fav else 'normal', border=(0,0,0,0)
            )
            star_button_popup.bind(on_press=partial(self.handle_star_press_in_hoca_popup_wrapper, site_id_from_meal, star_button_popup))
            title_star_layout.add_widget(star_button_popup)
        popup_content_main.add_widget(title_star_layout)

        if hoca_data and hoca_data.get('bilgi'):
            bilgi_scroll = ScrollView(size_hint=(1, 1))
            bilgi_label = Label(text=hoca_data.get('bilgi'), size_hint_y=None, halign='left', valign='top')
            bilgi_label.bind(texture_size=lambda i,s: setattr(i,'height',s[1]))
            bilgi_label.bind(width=lambda i,w: setattr(i,'text_size',(w,None)))
            bilgi_scroll.add_widget(bilgi_label)
            popup_content_main.add_widget(bilgi_scroll)
        else:
            no_info_label = Label(text=f"'{hoca_adi_sorgu}' için detaylı bilgi bulunamadı.")
            popup_content_main.add_widget(no_info_label)
        
        close_button = Button(text="Kapat", size_hint_y=None, height=dp(40))
        popup_content_main.add_widget(close_button)
        
        if self._current_hoca_info_popup: self._current_hoca_info_popup.dismiss()
        self._current_hoca_info_popup = Popup(title="Hoca Detayı", content=popup_content_main, size_hint=(0.9,0.8), auto_dismiss=True)
        close_button.bind(on_press=self._current_hoca_info_popup.dismiss)
        self._current_hoca_info_popup.bind(on_dismiss=lambda *args: setattr(self, '_current_hoca_info_popup', None))
        self._current_hoca_info_popup.open()

    def handle_star_press_in_hoca_popup_wrapper(self, site_id, toggle_button_instance, *args):
        app = App.get_running_app()
        if app: app.toggle_hoca_favorite(site_id, toggle_button_instance) 

    def set_error_message_on_header(self, message):
        if self.result_label: self.result_label.text = message
        self.update_status_console(f"HATA ARAYÜZ: {message}")

    def copy_arabic_text(self):

        text_to_copy = self.current_ayet_data.get('arapca_metin', "")
        if text_to_copy:
            try:
                Clipboard.copy(text_to_copy)
                self.update_status_console("Arapça metin panoya kopyalandı.")
            except Exception as e:
                self.update_status_console(f"Panoya kopyalanamadı: {e}")
        else:
            self.update_status_console("Kopyalanacak Arapça metin yok.")

    def copy_to_clipboard(self, text_to_copy, description):
        if text_to_copy:
            try: Clipboard.copy(text_to_copy)
            except Exception as e: self.update_status_console(f"Panoya kopyalanamadı: {e}")
            else: self.update_status_console(f"'{description}' panoya kopyalandı.")
        else: self.update_status_console("Kopyalanacak metin boş.")

    def clear_display_except_header(self, keep_header_message=False):
        if not keep_header_message and self.result_label: self.result_label.text = ""
        if self.arabic_label: self.arabic_label.text = ""; self.arabic_label.height = 0
        if self.transliteration_label: self.transliteration_label.text = ""; self.transliteration_label.height = 0
        if self.mealler_layout: self.mealler_layout.clear_widgets()
        if self.favorite_ayet_button: self.favorite_ayet_button.disabled = True; self.favorite_ayet_button.state = 'normal'

    def update_status_console(self, message):
        ayat_utils.cprint_debug(message, "KIVY_MAIN_STATUS")

    def open_read_mode_popup(self):
        current_s = self.current_sure_no_for_read_mode if self.current_sure_no_for_read_mode else None
        current_a = self.current_ayet_no_for_read_mode if self.current_ayet_no_for_read_mode else None
        popup = ReadModeStartPopup(main_screen_ref=self, current_sure_no=current_s, current_ayet_no=current_a, title="Okuma Modu Başlangıç", size_hint=(0.9,0.6))
        popup.open()

    def go_to_read_mode(self, sure_no, ayet_no):
        app = App.get_running_app()
        if app and app.root and hasattr(app.root, 'get_screen'):
            read_mode_screen = app.root.get_screen('read_mode')
            if read_mode_screen:
                read_mode_screen.start_reading(sure_no, ayet_no, None, 0) 
                app.root.current = 'read_mode'
                if hasattr(app.root, 'transition'): app.root.transition = FadeTransition(duration=0.3)
            else: self.update_status_console("HATA: 'read_mode' ekranı bulunamadı.")
        else: self.update_status_console("HATA: App root veya get_screen metodu bulunamadı.")
            
    def toggle_current_ayet_favorite(self):
        app = App.get_running_app()
        if self.current_ayet_data and self.current_ayet_data.get("sure_adi") != "Bulunamadı":
            sure_no = self.current_ayet_data.get('sure_no')
            ayet_no = self.current_ayet_data.get('ayet_no')
            sure_adi = self.current_ayet_data.get('sure_adi', '')
            ayet_kisa_str = self.current_ayet_data.get('ayet_numarasi_str', f"{ayet_no}. Ayet")

            if sure_no is not None and ayet_no is not None and sure_adi:
                if app:
                    app.toggle_ayet_favorite(sure_no, ayet_no, self.favorite_ayet_button)
            else:
                self.update_status_console(f"Favoriye eklemek için ayet bilgileri eksik.")
        else:
            self.update_status_console("Favoriye eklenecek mevcut ayet yok.")

class ReadModeNavPopup(Popup):
    """ReadModeScreen için ek navigasyon ve işlem seçeneklerini barındıran Popup."""
    read_mode_screen_ref = ObjectProperty(None)

    def __init__(self, read_mode_screen_ref, **kwargs):
        super().__init__(**kwargs)
        self.read_mode_screen_ref = read_mode_screen_ref

    def call_read_mode_method(self, method_name, *args):
        """ReadModeScreen'deki bir metodu çağırır ve popup'ı kapatır."""
        if self.read_mode_screen_ref and hasattr(self.read_mode_screen_ref, method_name):
            method = getattr(self.read_mode_screen_ref, method_name)
            method(*args)
            self.dismiss()
        else:
            ayat_utils.cprint_debug(f"HATA: ReadModeNavPopup, '{method_name}' metodunu çağıramadı.", "POPUP_CALLBACK_ERR")

class ReadModeScreen(Screen):
    return_to_subject_surah_name = StringProperty(None, allownone=True)
    return_to_subject_surah_no = NumericProperty(0)
    current_sure_name_for_display = StringProperty("Sure")
    header_label = ObjectProperty(None)
    arabic_read_label = ObjectProperty(None) 
    transliteration_read_label = ObjectProperty(None)
    mealler_read_layout = ObjectProperty(None)
    read_mode_jump_input = ObjectProperty(None)
    favorite_ayet_button_read = ObjectProperty(None) 
    
    word_analysis_mode = BooleanProperty(False)
    current_sure_no = NumericProperty(0)
    current_ayet_no = NumericProperty(0)
    current_ayet_data_read = DictProperty({})
    is_loading = BooleanProperty(False)
    _event_bound_fav_hocas_readmode = BooleanProperty(False)
    _event_bound_fav_ayets_read = BooleanProperty(False)
    _word_info_popup_read = ObjectProperty(None, allownone=True)
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        Clock.schedule_once(self._late_init_read_mode)

    def _dummy_ref_press_read(self, instance, ref_value):
        pass

    def load_current_ayet_for_read_mode(self, force_refresh=False):
        if self.is_loading:
            return
        
        if self.current_sure_no == 0 or self.current_ayet_no == 0:
            self._set_read_mode_error("Hata: Sure ve Ayet Numarası geçerli değil.")
            return

        self.is_loading = True
        sure_adi_baslik = ayat_utils.get_sure_name_db(self.current_sure_no) or f"Sure {self.current_sure_no}"
        self.current_sure_name_for_display = sure_adi_baslik # Buton metni için güncelle
        if self.header_label:
            self.header_label.text = f"{sure_adi_baslik} - {self.current_ayet_no}. Ayet (Yükleniyor...)"
        if self.arabic_read_label: self.arabic_read_label.text = "Yükleniyor..."
        if self.transliteration_read_label: self.transliteration_read_label.text = ""
        if self.mealler_read_layout: self.mealler_read_layout.clear_widgets()
        if self.favorite_ayet_button_read:
            self.favorite_ayet_button_read.disabled = True
            self.favorite_ayet_button_read.state = 'normal'

        def _fetch_data_on_thread():
            try:
                fetched_data = ayat_utils.get_complete_ayah_details_from_db(self.current_sure_no, self.current_ayet_no)
                Clock.schedule_once(lambda dt: self._display_ayet_in_read_mode(fetched_data))
            except Exception as e:
                tb_str = traceback.format_exc()
                error_msg_thread = f"Okuma Modu thread hatası: {e}\n{tb_str}"
                self.update_read_mode_status_console(error_msg_thread)
                Clock.schedule_once(lambda dt: self._set_read_mode_error(f"Ayet yüklenirken bir hata oluştu: {e}"))
            finally:
                Clock.schedule_once(lambda dt: setattr(self, 'is_loading', False))

        threading.Thread(target=_fetch_data_on_thread, daemon=True).start()

    def set_bookmark(self):
        """O anki ayeti 'kaldığım yer' olarak veritabanına kaydeder."""
        if not self.is_loading and self.current_sure_no and self.current_ayet_no:
            if ayat_utils.save_last_read_location(self.current_sure_no, self.current_ayet_no):
                # Kullanıcıya görsel geri bildirim verelim
                self.header_label.text = "✓ Yer işareti kaydedildi!"
                Clock.schedule_once(lambda dt: self._display_ayet_in_read_mode(self.current_ayet_data_read), 1.5)
            else:
                self.header_label.text = "Hata: İşaret kaydedilemedi!"
                Clock.schedule_once(lambda dt: self._display_ayet_in_read_mode(self.current_ayet_data_read), 2)

    def open_nav_popup(self):
        """Ek navigasyon seçeneklerini içeren popup'ı açar."""
        if self.is_loading:
            return
        popup = ReadModeNavPopup(read_mode_screen_ref=self)
        popup.open()

    def _late_init_read_mode(self, dt):
        app = App.get_running_app()
        if app:
            if not self._event_bound_fav_hocas_readmode:
                try: 
                    app.bind(on_favorite_hocas_changed=self.refresh_mealler_display_read_mode)
                    self._event_bound_fav_hocas_readmode = True
                except Exception as e: ayat_utils.cprint_debug(f"HATA: ReadMode on_favorite_hocas_changed bağlanamadı: {e}")
            
            if not self._event_bound_fav_ayets_read: 
                try: 
                    app.bind(on_favorite_ayets_changed=self.update_favorite_ayet_button_status_read)
                    self._event_bound_fav_ayets_read = True
                except Exception as e: ayat_utils.cprint_debug(f"HATA: ReadMode on_favorite_ayets_changed bağlanamadı: {e}")

    def return_to_subject_screen(self):
        if self.return_to_subject_surah_name and self.return_to_subject_surah_no != 0:
            app = App.get_running_app()
            if app and app.root:
                try:
                    subject_screen = app.root.get_screen('subject_selection')
                    subject_screen.load_subjects_for_surah_on_enter = self.return_to_subject_surah_name
                    
                    app.root.current = 'subject_selection'
                    app.root.transition = FadeTransition(duration=0.2)
                except Exception as e:
                    self.update_read_mode_status_console(f"HATA: Konu seçimine dönülürken: {e}")

    def refresh_mealler_display_read_mode(self, *args):
        if self.current_ayet_data_read and self.current_ayet_data_read.get("sure_adi") != "Bulunamadı":
            self._display_ayet_in_read_mode(dict(self.current_ayet_data_read))

    def update_favorite_ayet_button_status_read(self, *args):
        app = App.get_running_app()
        if self.favorite_ayet_button_read and self.current_ayet_data_read and app:
            if self.current_ayet_data_read.get("sure_adi") != "Bulunamadı":
                sure_no = self.current_sure_no 
                ayet_no = self.current_ayet_no 
                if sure_no and ayet_no:
                    is_fav = app.is_ayet_favorite(sure_no, ayet_no)
                    self.favorite_ayet_button_read.state = 'down' if is_fav else 'normal'
                    self.favorite_ayet_button_read.disabled = False
                else: 
                    self.favorite_ayet_button_read.disabled = True
                    self.favorite_ayet_button_read.state = 'normal'
            else: 
                self.favorite_ayet_button_read.disabled = True
                self.favorite_ayet_button_read.state = 'normal'
        elif self.favorite_ayet_button_read: 
            self.favorite_ayet_button_read.disabled = True
            self.favorite_ayet_button_read.state = 'normal'

    def start_reading(self, sure_no, ayet_no, came_from_subjects_surah_name=None, came_from_subjects_surah_no=0):
        self.current_sure_no = int(sure_no)
        self.current_ayet_no = int(ayet_no)
        self.word_analysis_mode = False 
        analysis_button = self.ids.get('analysis_toggle_button_read_mode')
        if analysis_button:
             analysis_button.text = "Kelime Analizini Aç"
        
        self.return_to_subject_surah_name = came_from_subjects_surah_name
        self.return_to_subject_surah_no = came_from_subjects_surah_no
        
        return_button = self.ids.get('return_to_subjects_button_read_mode_id')
        main_menu_btn = self.ids.get('ana_menuye_don_read_mode_btn_id')
        
        if return_button and main_menu_btn:
            if self.return_to_subject_surah_name:
                return_button.opacity = 1
                return_button.disabled = False
                return_button.size_hint_x = 0.5
                main_menu_btn.size_hint_x = 0.5
            else:
                return_button.opacity = 0
                return_button.disabled = True
                return_button.size_hint_x = 0
                return_button.width = 0
                main_menu_btn.size_hint_x = 1.0
        
        self.load_current_ayet_for_read_mode()

    def show_current_sure_subjects_popup(self):
        if self.is_loading:
            return

        if self.current_sure_no != 0 and self.current_sure_name_for_display not in ["Sure", "Bilinmeyen Sure"]:
            popup = SureSubjectsPopup(
                sure_no=self.current_sure_no,
                sure_name=self.current_sure_name_for_display,
                read_mode_ref=self
            )
            popup.open()
        else:
            self.update_read_mode_status_console("Konuları göstermek için geçerli bir sure yüklenmemiş.")

    def _display_ayet_in_read_mode(self, ayet_verisi_full_read):
        if not ayet_verisi_full_read or ayet_verisi_full_read.get("error"):
            error_msg = ayet_verisi_full_read.get("error", "Bilinmeyen hata") if ayet_verisi_full_read else "Veri boş"
            self._set_read_mode_error(f"Ayet detayı alınamadı: {error_msg}")
            return

        self.current_ayet_data_read = dict(ayet_verisi_full_read)
        
        if self.header_label:
            sure_adi_baslik = self.current_ayet_data_read.get('sure_adi', self.current_sure_name_for_display)
            ayet_no_baslik = self.current_ayet_data_read.get('ayet_numarasi_str', f"{self.current_ayet_no}. Ayet")
            self.header_label.text = f"{sure_adi_baslik} - {ayet_no_baslik}"
        
        self.update_favorite_ayet_button_status_read()
        
        if self.arabic_read_label:
            # Arapça metin etiketi artık statik bir mesaj gösterecek
            self.arabic_read_label.text = "Şu an için ayetin arapça metnini görüntüleyemiyoruz. Ana menüdeki 'Arapçayı Kopyala' butonunu kullanabilirsiniz."
            self.arabic_read_label.markup = False
            self.arabic_read_label.base_direction = None
            self.arabic_read_label.text_language = None
            self.arabic_read_label.halign = 'center'
            self.arabic_read_label.valign = 'middle'
            
        trans_data_read = self.current_ayet_data_read.get('transliterasyon', {})
        if self.transliteration_read_label:
            if trans_data_read and trans_data_read.get('metin'):
                self.transliteration_read_label.text = f"Transliterasyon:\n{trans_data_read.get('metin')}"
            else:
                self.transliteration_read_label.text = ""

        if self.mealler_read_layout:
            self.mealler_read_layout.clear_widgets()
            all_mealler_read = self.current_ayet_data_read.get('mealler', [])
            app = App.get_running_app()
            preferred_hoca_ids_read = app.user_settings.get("favorite_translator_ids", DEFAULT_READ_MODE_HOCA_IDS)
            max_favs_to_show_read = app.user_settings.get("max_favorites_limit", 3)
                
            displayed_meals = []
                # Önce favorileri ekle
            for hoca_id in preferred_hoca_ids_read:
                for meal in all_mealler_read:
                    if meal.get('id') == hoca_id and meal not in displayed_meals:
                        displayed_meals.append(meal)
                        break
                # Kalanları ekle
            for meal in all_mealler_read:
                if meal not in displayed_meals:
                    displayed_meals.append(meal)

            for meal_data in displayed_meals[:max_favs_to_show_read]:
                self._add_meal_to_read_mode_layout(meal_data)
                
            if not displayed_meals:
                self.mealler_read_layout.add_widget(Label(text="Bu ayet için meal bulunamadı."))

    def _add_meal_to_read_mode_layout(self, meal_data):
        if not self.mealler_read_layout: return
        app = App.get_running_app()
        hoca_adi_raw = meal_data.get('yazar_raw', 'Bilinmeyen Yazar')
        meal_metni = meal_data.get('metin', 'Meal bulunamadı.')
        site_id = meal_data.get('id')
        
        canonical_tam_ad = ayat_utils.site_id_to_hoca_tam_ad_haritasi.get(site_id.casefold()) if site_id else None
        goruntulenecek_ad = canonical_tam_ad if canonical_tam_ad and ayat_utils.hoca_veritabani.get(canonical_tam_ad) else hoca_adi_raw
        
        meal_entry_layout = BoxLayout(orientation='vertical', size_hint_y=None, spacing=dp(5))
        meal_entry_layout.bind(minimum_height=meal_entry_layout.setter('height'))
        
        hoca_header_layout = BoxLayout(orientation='horizontal', size_hint_y=None, height=dp(40), spacing=dp(5))
        is_fav_hoca = app.is_hoca_favorite(site_id) if site_id and app else False
        star_button = ToggleButton(background_normal=STAR_EMPTY_IMG, background_down=STAR_FILLED_IMG,
                                    size_hint_x=None, width=dp(36), state='down' if is_fav_hoca else 'normal', border=(0,0,0,0))
        if site_id and app: star_button.bind(on_press=partial(app.toggle_hoca_favorite, site_id, star_button))
        else: star_button.disabled = True

        hoca_name_label = Label(text=f"{goruntulenecek_ad}", size_hint_x=1, halign='left', valign='middle', font_size=dp(15))
        hoca_name_label.bind(text_size=lambda i,v: setattr(i,'text_size',(i.width-dp(10),None)))
        
        main_screen_ref = App.get_running_app().root.get_screen('main') if App.get_running_app() and App.get_running_app().root else None
        if main_screen_ref: hoca_name_label.bind(on_touch_down=partial(main_screen_ref.trigger_hoca_info_popup_from_label, goruntulenecek_ad, canonical_tam_ad, site_id))
        
        hoca_header_layout.add_widget(star_button)
        hoca_header_layout.add_widget(hoca_name_label)
        
        meal_text_input = TextInput(text=meal_metni, readonly=True, multiline=True, size_hint_y=None,
                                    background_color=(0.98,0.98,0.98,1), foreground_color=(0.1,0.1,0.1,1), font_size=dp(16))
        meal_text_input.bind(minimum_height=meal_text_input.setter('height'))
        
        meal_entry_layout.add_widget(hoca_header_layout)
        meal_entry_layout.add_widget(meal_text_input)
        self.mealler_read_layout.add_widget(meal_entry_layout)

    def _set_read_mode_error(self, message):
        if self.header_label: self.header_label.text = message
        if self.arabic_read_label: 
            self.arabic_read_label.text = "Veri yüklenemedi."
            self.arabic_read_label.height = self.arabic_read_label.texture_size[1] + dp(15) if self.arabic_read_label.text else 0
        if self.transliteration_read_label: self.transliteration_read_label.text = ""; self.transliteration_read_label.height = 0
        if self.mealler_read_layout: self.mealler_read_layout.clear_widgets()
        self.update_read_mode_status_console(f"HATA Okuma Modu: {message}")
    
    # DÜZELTME: Bu fonksiyonun tamamı, değişkenlerin doğru kapsama alanında olmasını sağlamak
    # ve her koşulu (sure başı/sonu, Kur'an başı/sonu) net bir şekilde ele almak için yeniden yazıldı.
    def navigate_ayet(self, delta):
        if self.is_loading or self.current_sure_no == 0:
            self.update_read_mode_status_console("Navigasyon engellendi: Yükleniyor veya sure seçili değil.")
            return

        new_ayet_no = self.current_ayet_no + delta
        max_ayets_in_current_sure = ayat_utils.get_ayah_count_db(self.current_sure_no)

        if 1 <= new_ayet_no <= max_ayets_in_current_sure:
            # Sure içinde normal geçiş
            self.current_ayet_no = new_ayet_no
            self.load_current_ayet_for_read_mode()
        elif new_ayet_no > max_ayets_in_current_sure:
            # Sonraki sureye geçiş
            if self.current_sure_no >= 114:
                self.update_read_mode_status_console("Kur'an'ın sonuna ulaşıldı.")
                return
            self.current_sure_no += 1
            self.current_ayet_no = 1
            self.load_current_ayet_for_read_mode()
        elif new_ayet_no < 1:
            # Önceki sureye geçiş
            if self.current_sure_no <= 1:
                self.update_read_mode_status_console("Kur'an'ın başına ulaşıldı.")
                return
            self.current_sure_no -= 1
            # Yeni surenin son ayetine git
            self.current_ayet_no = ayat_utils.get_ayah_count_db(self.current_sure_no) or 1
            self.load_current_ayet_for_read_mode()

    # DÜZELTME: Bu fonksiyon, daha basit ve okunabilir olması için yeniden düzenlendi.
    def navigate_surah(self, delta):
        if self.is_loading:
            self.update_read_mode_status_console("Navigasyon engellendi: Yükleniyor.")
            return
        
        if self.current_sure_no == 0 and delta < 0:
            self.update_read_mode_status_console("Önce bir sure ve ayet yükleyin.")
            return
            
        target_sure_no = self.current_sure_no + delta
        
        if target_sure_no > 114:
            self.update_read_mode_status_console("Zaten son suredesiniz.")
            target_sure_no = 114
        
        if target_sure_no < 1:
            self.update_read_mode_status_console("Zaten ilk suredesiniz.")
            target_sure_no = 1

        if target_sure_no != self.current_sure_no:
            self.current_sure_no = target_sure_no
            self.current_ayet_no = 1
            self.load_current_ayet_for_read_mode()

    def go_to_surah_start(self):
        if self.is_loading or self.current_sure_no == 0: return
        if self.current_ayet_no == 1: 
            self.update_read_mode_status_console("Zaten surenin ilk ayetindesiniz.")
            return
        self.current_ayet_no = 1
        self.load_current_ayet_for_read_mode()
        
    def go_to_surah_end(self):
        if self.is_loading or self.current_sure_no == 0: return
        max_ayet = ayat_utils.get_ayah_count_db(self.current_sure_no)
        if max_ayet:
            if self.current_ayet_no == max_ayet: 
                self.update_read_mode_status_console("Zaten surenin son ayetindesiniz.")
                return
            self.current_ayet_no = max_ayet
            self.load_current_ayet_for_read_mode()
        else:
            self.update_read_mode_status_console(f"HATA: {self.current_sure_no} için ayet sayısı bulunamadı.")

    def jump_to_ayet_button_pressed(self):
        if self.is_loading or not self.read_mode_jump_input: return
        
        sorgu_str = self.read_mode_jump_input.text.strip()
        original_hint = self.read_mode_jump_input.hint_text 
        
        if not sorgu_str:
            self.read_mode_jump_input.hint_text = "Lütfen giriş yapın!"
            Clock.schedule_once(lambda dt: setattr(self.read_mode_jump_input, 'hint_text', original_hint), 2)
            return
            
        sure_no, ayet_no_list, is_range = ayat_utils.parse_sure_ayet_input(sorgu_str)
        if sure_no and ayet_no_list and not is_range: 
            ayet_no = ayet_no_list[0]
            self.start_reading(sure_no, ayet_no)
            self.read_mode_jump_input.text = "" 
        else:
            self.read_mode_jump_input.text = ""
            self.read_mode_jump_input.hint_text = "GEÇERSİZ! (Örn: Yasin 12)"
            Clock.schedule_once(lambda dt: setattr(self.read_mode_jump_input, 'hint_text', original_hint), 2)
            
    def go_to_main_menu(self):
        app = App.get_running_app()
        if app and app.root: 
            app.root.current = 'main'

    def update_read_mode_status_console(self, message):
        ayat_utils.cprint_debug(message, "KIVY_READ_MODE")

    def toggle_current_ayet_favorite_read_mode(self):
        app = App.get_running_app()
        if self.current_ayet_data_read and self.current_ayet_data_read.get("sure_adi") != "Bulunamadı":
            sure_no = self.current_sure_no
            ayet_no = self.current_ayet_no
            if sure_no and ayet_no and app:
                app.toggle_ayet_favorite(sure_no, ayet_no, self.favorite_ayet_button_read)
        else:
            self.update_read_mode_status_console("Favoriye eklenecek mevcut ayet yok.")
    
class HistoryScreen(Screen):
    history_layout = ObjectProperty(None)
    _event_bound_fav_ayets_history_screen = BooleanProperty(False)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        Clock.schedule_once(self._late_init_history_screen)

    def _late_init_history_screen(self, dt):
        app = App.get_running_app()
        if app and hasattr(app, 'on_favorite_ayets_changed') and not self._event_bound_fav_ayets_history_screen:
            try:
                app.bind(on_favorite_ayets_changed=self._handle_app_fav_ayets_changed_history)
                self._event_bound_fav_ayets_history_screen = True
            except Exception as e:
                ayat_utils.cprint_debug(f"HATA: HistoryScreen on_favorite_ayets_changed bağlanamadı: {e}")

    def on_pre_leave(self, *args):
        super().on_pre_leave(*args)
        app = App.get_running_app()
        if app and self._event_bound_fav_ayets_history_screen:
            try:
                app.unbind(on_favorite_ayets_changed=self._handle_app_fav_ayets_changed_history)
                self._event_bound_fav_ayets_history_screen = False
            except Exception as e:
                 ayat_utils.cprint_debug(f"HATA: HistoryScreen on_favorite_ayets_changed ayrılırken: {e}")

    def _handle_app_fav_ayets_changed_history(self, *args):
        if self.manager and self.manager.current == self.name:
            self.populate_history()

    def on_enter(self, *args):
        super().on_enter(*args)
        self.populate_history()

    def toggle_favorite_from_history(self, s_no, a_no, button_instance, *args):
        app = App.get_running_app()
        if app:
            app.toggle_ayet_favorite(s_no, a_no, button_instance)

    def populate_history(self):
        if not self.history_layout:
            return
        self.history_layout.clear_widgets()

        if not ayat_utils.query_history:
            no_history_label = Label(text="Geçmiş yok.", size_hint_y=None, height=dp(30))
            self.history_layout.add_widget(no_history_label)
            return

        app = App.get_running_app()

        for (sorgu_id, s_no, a_no, s_adi, _) in list(ayat_utils.query_history):
            item_row_layout = BoxLayout(orientation='horizontal', size_hint_y=None, height=dp(50), spacing=dp(5), padding=(dp(5),0,dp(5),0))
            btn_text = f"{s_adi} Suresi {a_no}. Ayet" 
            open_ayet_button = Button(text=btn_text, size_hint_x=0.65, halign='left', valign='middle')
            open_ayet_button.bind(text_size=lambda i, v: setattr(i, 'text_size', (i.width - dp(10), None)))
            open_ayet_button.bind(on_press=partial(self.load_ayet_from_history, s_no, a_no))
            item_row_layout.add_widget(open_ayet_button)

            is_currently_favorite = app.is_ayet_favorite(s_no, a_no) if app else False
            favorite_button = ToggleButton(
                size_hint_x=None, width=dp(44),
                background_normal=app.HEART_EMPTY_IMG, background_down=app.HEART_FILLED_IMG,
                state='down' if is_currently_favorite else 'normal', border=(0,0,0,0)
            )
            favorite_button.bind(on_press=partial(self.toggle_favorite_from_history, s_no, a_no, favorite_button))
            item_row_layout.add_widget(favorite_button)

            delete_history_button = Button(text="Sil", size_hint_x=None, width=dp(60), background_color=(0.8, 0.3, 0.3, 1))
            delete_history_button.bind(on_press=partial(self.delete_item_from_history, sorgu_id))
            item_row_layout.add_widget(delete_history_button)

            self.history_layout.add_widget(item_row_layout)

    def delete_item_from_history(self, sorgu_id_to_delete, *args):
        if ayat_utils.delete_single_history_entry_db(sorgu_id_to_delete):
            self.populate_history()
        else:
            self.update_status_console_local(f"HATA: Sorgu ID {sorgu_id_to_delete} geçmişten silinemedi.")

    def load_ayet_from_history(self, sure_no, ayet_no, *args):
        app_ref = App.get_running_app()
        if not app_ref or not app_ref.root : return
        main_screen = app_ref.root.get_screen('main')
        if main_screen and main_screen.sorgu_input:
            sure_adi_display = ayat_utils.get_sure_name_db(sure_no) or str(sure_no)
            main_screen.sorgu_input.text = f"{sure_adi_display} {ayet_no}"
            main_screen.fetch_ayet_data(sure_no, ayet_no, context_message="(Geçmişten)")
        app_ref.root.current = 'main'
        if hasattr(app_ref.root, 'transition'): app_ref.root.transition = FadeTransition(duration=0.3)

    def update_status_console_local(self, message):
        ayat_utils.cprint_debug(message, "KIVY_HISTORY")

class FavoriteAyetsScreen(Screen):
    favorite_ayets_layout = ObjectProperty(None)
    _event_bound_fav_ayets_screen = BooleanProperty(False)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        Clock.schedule_once(self._late_init_fav_ayets)

    def _late_init_fav_ayets(self, dt):
        app = App.get_running_app()
        if app and not self._event_bound_fav_ayets_screen:
            try:
                app.bind(on_favorite_ayets_changed=self._handle_app_fav_ayets_changed)
                self._event_bound_fav_ayets_screen = True
            except Exception as e:
                ayat_utils.cprint_debug(f"HATA: FavoriteAyetsScreen on_favorite_ayets_changed bağlanamadı: {e}")

    def _handle_app_fav_ayets_changed(self, *args):
        if self.manager and self.manager.current == self.name:
            self.populate_favorites()

    def on_enter(self, *args):
        super().on_enter(*args)
        self.populate_favorites()

    def populate_favorites(self):
        if not self.favorite_ayets_layout:
            return
        self.favorite_ayets_layout.clear_widgets()
        app = App.get_running_app()
        
        if not app or not app.favorite_ayets:
            no_favorites_label = Label(text="Henüz favori ayetiniz yok.", size_hint_y=None, height=dp(60))
            self.favorite_ayets_layout.add_widget(no_favorites_label)
            return

        for (s_no, a_no, s_adi, _) in app.favorite_ayets:
            row_layout = BoxLayout(orientation='horizontal', size_hint_y=None, height=dp(55), spacing=dp(10))
            info_text = f"{s_adi} Suresi {a_no}. Ayet"
            info_label = Label(text=info_text, size_hint_x=0.6, halign='left', valign='middle')
            info_label.bind(width=lambda i, v: setattr(i, 'text_size', (i.width * 0.95, None)))
            
            open_button = Button(text="Aç", size_hint_x=0.2, font_size=dp(14))
            open_button.bind(on_press=partial(self.go_to_ayet, s_no, a_no))
            
            remove_button = Button(text="Sil", size_hint_x=0.2, background_color=(0.9, 0.4, 0.4, 1), font_size=dp(14))
            remove_button.bind(on_press=partial(self.remove_ayet_from_favorites, s_no, a_no))
            
            row_layout.add_widget(info_label)
            row_layout.add_widget(open_button)
            row_layout.add_widget(remove_button)
            self.favorite_ayets_layout.add_widget(row_layout)

    def go_to_ayet(self, sure_no, ayet_no, *args):
        app_ref = App.get_running_app()
        if not app_ref or not app_ref.root : return
        main_screen = app_ref.root.get_screen('main')
        if main_screen and main_screen.sorgu_input:
            sure_adi_display = ayat_utils.get_sure_name_db(sure_no) or str(sure_no)
            main_screen.sorgu_input.text = f"{sure_adi_display} {ayet_no}"
            main_screen.fetch_ayet_data(sure_no, ayet_no, context_message="(Favorilerden)")
        app_ref.root.current = 'main'
        if hasattr(app_ref.root, 'transition'): app_ref.root.transition = FadeTransition(duration=0.3)

    def remove_ayet_from_favorites(self, sure_no, ayet_no, *args):
        app = App.get_running_app()
        if app: app.toggle_ayet_favorite(sure_no, ayet_no, None)

    def go_to_main_menu(self):
        app = App.get_running_app()
        if app and app.root:
            app.root.current = 'main'
            
    def update_status_console_local(self, message):
        ayat_utils.cprint_debug(message, "KIVY_FAVORITES")

class SettingsScreen(Screen):
    favorite_hocas_layout = ObjectProperty(None)
    status_message_settings = ObjectProperty(None)
    max_favorites_slider = ObjectProperty(None)
    max_favorites_value_label = ObjectProperty(None)
    _temp_selected_favorite_ids = ListProperty([])

    def on_pre_enter(self):
        super().on_pre_enter()
        app = App.get_running_app()
        if not app: return
        self._temp_selected_favorite_ids = list(app.user_settings.get("favorite_translator_ids", []))
        current_max_limit = app.user_settings.get("max_favorites_limit", 3)
        if self.max_favorites_slider: self.max_favorites_slider.value = current_max_limit
        if self.max_favorites_value_label: self.max_favorites_value_label.text = str(int(current_max_limit))
        if not self.favorite_hocas_layout:
            return
        self.favorite_hocas_layout.clear_widgets()
        self.update_status_message("")
        if not ayat_utils.hoca_veritabani:
            self.favorite_hocas_layout.add_widget(Label(text="Hoca listesi yüklenemedi."))
            return
        sorted_hoca_names = sorted(ayat_utils.hoca_veritabani.keys())
        for hoca_name in sorted_hoca_names:
            hoca_data = ayat_utils.hoca_veritabani[hoca_name]
            primary_site_id = hoca_data.get("site_idler", [None])[0]
            if not primary_site_id: continue
            row = BoxLayout(orientation='horizontal', size_hint_y=None, height=dp(40), spacing=dp(10))
            hoca_label = Label(text=hoca_name, size_hint_x=0.75, halign='left', valign='middle', shorten=True, shorten_from='right')
            hoca_label.bind(text_size=lambda i,v: setattr(i,'text_size',(i.width,None)))
            is_fav = primary_site_id in self._temp_selected_favorite_ids
            toggle_btn = ToggleButton(text="Favori", size_hint_x=0.25, state='down' if is_fav else 'normal')
            toggle_btn.bind(on_press=partial(self.handle_hoca_toggle, primary_site_id, toggle_btn))
            row.add_widget(hoca_label)
            row.add_widget(toggle_btn)
            self.favorite_hocas_layout.add_widget(row)

    def handle_hoca_toggle(self, site_id_to_toggle, toggle_button_instance, *args):
        self.update_status_message("")
        app = App.get_running_app()
        if not app: return

        # Ayarları doğrudan app.user_settings üzerinden alalım
        current_favorites = list(app.user_settings.get("favorite_translator_ids", []))
        max_limit = app.user_settings.get("max_favorites_limit", 3)

        if toggle_button_instance.state == 'down':
            if site_id_to_toggle not in current_favorites:
                if len(current_favorites) < max_limit:
                    current_favorites.append(site_id_to_toggle)
                else:
                    toggle_button_instance.state = 'normal' # Butonu geri eski haline getir
                    self.update_status_message(f"En fazla {max_limit} favori seçebilirsiniz.")
                    Clock.schedule_once(lambda dt: self.update_status_message(""), 3)
                    return # Kaydetme işlemi yapmadan çık
        else: # Toggle 'normal' durumdaysa (kullanıcı favoriden çıkardıysa)
            if site_id_to_toggle in current_favorites:
                current_favorites.remove(site_id_to_toggle)
        
        # --- YENİ EKLENEN ANINDA KAYDETME MANTIĞI ---
        app.user_settings['favorite_translator_ids'] = current_favorites
        if ayat_utils.save_user_settings(app.user_settings):
            self.update_status_message("Favori listesi güncellendi.")
            Clock.schedule_once(lambda dt: self.update_status_message(""), 2)
            app.dispatch('on_favorite_hocas_changed')
        else:
            self.update_status_message("HATA: Ayarlar kaydedilemedi!")
            Clock.schedule_once(lambda dt: self.update_status_message(""), 3)

    def update_max_favorites_label(self, value):
        # Bu fonksiyon artık sadece görsel olarak etiketi günceller
        if self.max_favorites_value_label:
            self.max_favorites_value_label.text = str(int(value))

    def save_slider_setting(self, slider_instance):
        # Bu yeni fonksiyon, kullanıcı slider'ı bıraktığında çalışır
        app = App.get_running_app()
        if not app: return

        new_max_limit = int(slider_instance.value)
        app.user_settings['max_favorites_limit'] = new_max_limit
        
        # Eğer mevcut favori sayısı yeni limitten fazlaysa, favori listesini kırp
        current_favorites = list(app.user_settings.get("favorite_translator_ids", []))
        if len(current_favorites) > new_max_limit:
            app.user_settings['favorite_translator_ids'] = current_favorites[:new_max_limit]
            # Arayüzü yenilemek için on_pre_enter'ı tekrar çağır
            self.on_pre_enter()
        
        # Değişiklikleri veritabanına kaydet
        if ayat_utils.save_user_settings(app.user_settings):
            self.update_status_message(f"Max favori sayısı {new_max_limit} olarak ayarlandı.")
            Clock.schedule_once(lambda dt: self.update_status_message(""), 2)
            app.dispatch('on_favorite_hocas_changed')
        else:
            self.update_status_message("HATA: Ayarlar kaydedilemedi!")
            Clock.schedule_once(lambda dt: self.update_status_message(""), 3)

    def update_status_message(self, message):
        if self.status_message_settings: self.status_message_settings.text = message

    def clear_cache_button_pressed(self):
        result_status = ayat_utils.clear_ayet_cache_file()
        status_message = ""
        if result_status == "all_success": status_message = "Önbellek ve geçmiş temizlendi."
        elif result_status == "cache_only_success": status_message = "Önbellek temizlendi, geçmişte sorun oldu."
        elif result_status == "history_only_success": status_message = "Geçmiş temizlendi, önbellekte sorun oldu."
        else: status_message = "HATA: Önbellek ve geçmiş temizlenemedi."

        self.update_status_message(status_message)
        Clock.schedule_once(lambda dt: self.update_status_message(""), 3)

class KuranApp(App, EventDispatcher):
    ARABIC_FONT_NAME = StringProperty('fonts/NotoNaskhArabic-VariableFont_wght.ttf')
    user_settings = DictProperty({})
    favorite_ayets = ListProperty([]) 
    HEART_EMPTY_IMG = StringProperty(HEART_EMPTY_IMG) 
    HEART_FILLED_IMG = StringProperty(HEART_FILLED_IMG)
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.register_event_type('on_favorite_hocas_changed')
        self.register_event_type('on_favorite_ayets_changed') 

    def on_favorite_hocas_changed(self, *args):
        pass

    def on_favorite_ayets_changed(self, *args): 
        pass

    def build(self):
        sm = ScreenManager(transition=FadeTransition(duration=0.2))
        sm.add_widget(MainScreen(name='main'))
        sm.add_widget(SettingsScreen(name='settings'))
        sm.add_widget(HistoryScreen(name='history'))
        sm.add_widget(ReadModeScreen(name='read_mode'))
        sm.add_widget(FavoriteAyetsScreen(name='favorite_ayets'))
        sm.add_widget(SubjectSelectionScreen(name='subject_selection'))
        sm.add_widget(AIScreen(name='ai_screen')) # <-- BU SATIRI EKLEYİN
        return sm

    def on_start(self):
        ayat_utils.hoca_veritabani_yukle()
        ayat_utils.load_query_history()
        ayat_utils.load_quran_corpus_data()
        self.user_settings = ayat_utils.load_user_settings()
        self.favorite_ayets = ayat_utils.load_favorite_ayets()
        self.dispatch('on_favorite_hocas_changed') 
        self.dispatch('on_favorite_ayets_changed') 
    
    def on_stop(self):
        ayat_utils.save_user_settings(self.user_settings)

    def is_hoca_favorite(self, site_id):
        if not site_id: return False
        return site_id in self.user_settings.get("favorite_translator_ids", [])

    def toggle_hoca_favorite(self, site_id_to_toggle, star_button_instance=None, *args):
        if not site_id_to_toggle:
            return False
        
        current_settings = dict(self.user_settings) 
        temp_favorites = list(current_settings.get("favorite_translator_ids", []))
        max_limit = current_settings.get("max_favorites_limit", 3)
        
        if site_id_to_toggle in temp_favorites:
            temp_favorites.remove(site_id_to_toggle)
        else:
            if len(temp_favorites) < max_limit:
                temp_favorites.append(site_id_to_toggle)
            else:
                manage_popup = ManageFavoritesPopup(title="Favori Limiti Dolu", size_hint=(0.9,0.8), 
                                                 app_ref=self, site_id_to_add_later=site_id_to_toggle)
                manage_popup.open()
                if star_button_instance: star_button_instance.state = 'normal' 
                return
        
        current_settings["favorite_translator_ids"] = temp_favorites
        self.user_settings = current_settings 
        if ayat_utils.save_user_settings(self.user_settings): 
            self.dispatch('on_favorite_hocas_changed')
        
        if star_button_instance:
            star_button_instance.state = 'down' if self.is_hoca_favorite(site_id_to_toggle) else 'normal'

    def is_ayet_favorite(self, sure_no, ayet_no):
        if not sure_no or not ayet_no: return False
        for fav_ayet_tuple in self.favorite_ayets:
            if isinstance(fav_ayet_tuple, tuple) and len(fav_ayet_tuple) >= 2:
                try:
                    if int(fav_ayet_tuple[0]) == int(sure_no) and int(fav_ayet_tuple[1]) == int(ayet_no):
                        return True
                except (ValueError, TypeError):
                    continue
        return False

    def toggle_ayet_favorite(self, sure_no, ayet_no, fav_ayet_button_instance=None, *args):
        try:
            s_no_int = int(sure_no)
            a_no_int = int(ayet_no)
        except (ValueError, TypeError):
            self.update_status_console(f"HATA: toggle_ayet_favorite - geçersiz sure/ayet no.")
            return

        conn = None
        try:
            conn = sqlite3.connect(ayat_utils.DATABASE_FILE)
            cursor = conn.cursor()
            cursor.execute("SELECT ayah_db_id FROM Ayahs WHERE surah_number = ? AND ayah_number_in_surah = ?", (s_no_int, a_no_int))
            row = cursor.fetchone()
            if not row:
                self.update_status_console(f"HATA: {s_no_int}:{a_no_int} için ayah_db_id bulunamadı.")
                return
            ayah_db_id = row[0]

            cursor.execute("SELECT COUNT(*) FROM FavoriAyetler WHERE ayah_db_id = ?", (ayah_db_id,))
            is_currently_fav = cursor.fetchone()[0] > 0
            
            if is_currently_fav:
                cursor.execute("DELETE FROM FavoriAyetler WHERE ayah_db_id = ?", (ayah_db_id,))
            else:
                cursor.execute("INSERT INTO FavoriAyetler (ayah_db_id) VALUES (?)", (ayah_db_id,))
            conn.commit()
            
            self.favorite_ayets = ayat_utils.load_favorite_ayets()
            self.dispatch('on_favorite_ayets_changed')
        except sqlite3.Error as e:
            if conn: conn.rollback()
            self.update_status_console(f"HATA: toggle_ayet_favorite SQLite hatası: {e}")
        finally:
            if conn: conn.close()
            
        if fav_ayet_button_instance:
            fav_ayet_button_instance.state = 'down' if not is_currently_fav else 'normal'

    def update_status_console(self, message):
        ayat_utils.cprint_debug(message, "KIVY_APP")

if __name__ == '__main__':
    KuranApp().run()
