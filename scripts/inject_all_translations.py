#!/usr/bin/env python3
"""inject_all_translations.py — Fill 976 missing i18n keys in 17 locale files.
zh-CN: Traditional→Simplified conversion from zh-TW source.
Other: targeted translations for critical UI keys; English fallback for rest.
"""
import json, sys
from pathlib import Path
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT    = Path(__file__).parent.parent
LOCALES = ROOT / "src" / "chainlit_app" / "locales"

EN = json.loads((LOCALES / "en-US.json").read_text(encoding="utf-8"))
TW = json.loads((LOCALES / "zh-TW.json").read_text(encoding="utf-8"))

_sample = json.loads((LOCALES / "ar-SA.json").read_text(encoding="utf-8"))
MISSING = [k for k in EN if not k.startswith("_commands.") and k not in _sample]

T2S = str.maketrans(
    "資訊資料檔案視窗設定確認取消儲存顯示搜尋彙總稽核品質醫療器材"
    "標準規範準則符合評估診斷報告分析管理維護使用者帳號權限驗證憑證"
    "審核批准審查稽查查核記錄紀錄日誌歷史追蹤追溯版本進版異動變更"
    "修訂修改修正錯誤失敗故障缺陷差距差異偏差警告警示完成成功通過"
    "建立建置設計計畫規劃排程時程進度狀態條件要求需求備註說明提示"
    "指引標籤標記標號識別碼編號序號清單列表表格表單格式欄位標題頁面"
    "視圖介面畫面螢幕顯示器按鈕功能操作執行啟動停止暫停繼續重試重新"
    "重設清除刪除移除提取匯出匯入輸出輸入下載上傳傳送發送接收拒絕"
    "返回完整全部選取選擇選項已完成正在載入處理中請稍候請注意注意"
    "資料庫系統平台服務伺服器網路連線目前當前位置路徑引用參考對應",
    "资讯资料档案视窗设定确认取消储存显示搜寻汇总稽核品质医疗器材"
    "标准规范准则符合评估诊断报告分析管理维护使用者帐号权限验证凭证"
    "审核批准审查稽查查核记录纪录日志历史追踪追溯版本进版异动变更"
    "修订修改修正错误失败故障缺陷差距差异偏差警告警示完成成功通过"
    "建立建置设计计划规划排程时程进度状态条件要求需求备注说明提示"
    "指引标签标记标号识别码编号序号清单列表表格表单格式栏位标题页面"
    "视图界面画面荧幕显示器按钮功能操作执行启动停止暂停继续重试重新"
    "重设清除删除移除提取汇出汇入输出输入下载上传传送发送接收拒绝"
    "返回完整全部选取选择选项已完成正在载入处理中请稍候请注意注意"
    "资料库系统平台服务伺服器网路连线目前当前位置路径引用参考对应",
)
_MULTI = [
    ("醫療器材","医疗器械"),("品質管理","质量管理"),("品質管制","质量控制"),
    ("稽核記錄","审核记录"),("法規標準","法规标准"),("法規更新","法规更新"),
    ("文件管制","文件管制"),("交叉驗證","交叉验证"),("引用清單","引用清单"),
    ("進版引用","版本引用"),("匯出時間","导出时间"),("系統日誌","系统日志"),
    ("處理中","处理中"),("載入中","加载中"),("Markdown 檔案","Markdown 文件"),
    ("醫療院所","医疗机构"),("不符合","不符合"),("追溯性","可追溯性"),
]

def t2s(v):
    if isinstance(v, str):
        r = v.translate(T2S)
        for a,b in _MULTI: r=r.replace(a,b)
        return r
    if isinstance(v, list): return [t2s(x) for x in v]
    return v

def _v(k, d): return d.get(k, EN.get(k, ""))

# ── Targeted translations per language (btn.*, pipeline.*, ui.* priority) ──
_BTNS = {
    "fr-FR": ("Confirmer","Annuler","Enregistrer","Fermer","Exporter","Télécharger","Téléverser","Réessayer","Retour","Suivant","Soumettre","Réinitialiser","Modifier","Supprimer","Ajouter","Rechercher","Filtrer","Actualiser"),
    "de-DE": ("Bestätigen","Abbrechen","Speichern","Schließen","Exportieren","Herunterladen","Hochladen","Wiederholen","Zurück","Weiter","Einreichen","Zurücksetzen","Bearbeiten","Löschen","Hinzufügen","Suchen","Filtern","Aktualisieren"),
    "es-ES": ("Confirmar","Cancelar","Guardar","Cerrar","Exportar","Descargar","Subir","Reintentar","Atrás","Siguiente","Enviar","Restablecer","Editar","Eliminar","Añadir","Buscar","Filtrar","Actualizar"),
    "pt-BR": ("Confirmar","Cancelar","Salvar","Fechar","Exportar","Baixar","Enviar","Tentar novamente","Voltar","Próximo","Enviar","Redefinir","Editar","Excluir","Adicionar","Pesquisar","Filtrar","Atualizar"),
    "it-IT": ("Conferma","Annulla","Salva","Chiudi","Esporta","Scarica","Carica","Riprova","Indietro","Avanti","Invia","Ripristina","Modifica","Elimina","Aggiungi","Cerca","Filtra","Aggiorna"),
    "ru-RU": ("Подтвердить","Отмена","Сохранить","Закрыть","Экспорт","Скачать","Загрузить","Повторить","Назад","Далее","Отправить","Сбросить","Редактировать","Удалить","Добавить","Поиск","Фильтр","Обновить"),
    "ar-SA": ("تأكيد","إلغاء","حفظ","إغلاق","تصدير","تنزيل","رفع","إعادة المحاولة","رجوع","التالي","إرسال","إعادة تعيين","تعديل","حذف","إضافة","بحث","تصفية","تحديث"),
    "hi-IN": ("पुष्टि करें","रद्द करें","सहेजें","बंद करें","निर्यात","डाउनलोड","अपलोड","पुनः प्रयास","वापस","अगला","सबमिट","रीसेट","संपादित करें","हटाएं","जोड़ें","खोजें","फ़िल्टर","रीफ्रेश"),
    "th-TH": ("ยืนยัน","ยกเลิก","บันทึก","ปิด","ส่งออก","ดาวน์โหลด","อัปโหลด","ลองใหม่","กลับ","ถัดไป","ส่ง","รีเซ็ต","แก้ไข","ลบ","เพิ่ม","ค้นหา","กรอง","รีเฟรช"),
    "vi-VN": ("Xác nhận","Hủy","Lưu","Đóng","Xuất","Tải xuống","Tải lên","Thử lại","Quay lại","Tiếp theo","Gửi","Đặt lại","Chỉnh sửa","Xóa","Thêm","Tìm kiếm","Lọc","Làm mới"),
    "id-ID": ("Konfirmasi","Batal","Simpan","Tutup","Ekspor","Unduh","Unggah","Coba lagi","Kembali","Berikutnya","Kirim","Reset","Edit","Hapus","Tambah","Cari","Filter","Segarkan"),
    "ms-MY": ("Sahkan","Batal","Simpan","Tutup","Eksport","Muat turun","Muat naik","Cuba lagi","Kembali","Seterusnya","Hantar","Set semula","Edit","Padam","Tambah","Cari","Tapis","Muat semula"),
    "tr-TR": ("Onayla","İptal","Kaydet","Kapat","Dışa Aktar","İndir","Yükle","Yeniden Dene","Geri","İleri","Gönder","Sıfırla","Düzenle","Sil","Ekle","Ara","Filtrele","Yenile"),
    "nl-NL": ("Bevestigen","Annuleren","Opslaan","Sluiten","Exporteren","Downloaden","Uploaden","Opnieuw","Terug","Volgende","Indienen","Opnieuw instellen","Bewerken","Verwijderen","Toevoegen","Zoeken","Filteren","Vernieuwen"),
    "pl-PL": ("Potwierdź","Anuluj","Zapisz","Zamknij","Eksportuj","Pobierz","Prześlij","Ponów","Wstecz","Dalej","Wyślij","Resetuj","Edytuj","Usuń","Dodaj","Szukaj","Filtruj","Odśwież"),
    "ko-KR": ("확인","취소","저장","닫기","내보내기","다운로드","업로드","재시도","뒤로","다음","제출","초기화","편집","삭제","추가","검색","필터","새로 고침"),
}
_BTN_KEYS = ["btn.confirm","btn.cancel","btn.save","btn.close","btn.export","btn.download",
             "btn.upload","btn.retry","btn.back","btn.next","btn.submit","btn.reset",
             "btn.edit","btn.delete","btn.add","btn.search","btn.filter","btn.refresh"]

def _make_lang(lang_code: str) -> dict:
    result = {}
    btns = _BTNS.get(lang_code, ())
    btn_map = {k: f"✅ {v}" if i==0 else f"❌ {v}" if i==1 else v
               for i,(k,v) in enumerate(zip(_BTN_KEYS, btns))}
    # btn.confirm gets ✅, btn.cancel gets ❌, rest plain
    if btns:
        btn_map = {}
        icons = ["✅","❌","💾","✖","📥","⬇","⬆","🔄","←","→","","","✏","🗑","➕","🔍","⚙","🔄"]
        for i,(k,v) in enumerate(zip(_BTN_KEYS, btns)):
            ic = icons[i]
            btn_map[k] = f"{ic} {v}".strip() if ic else v
    for k in MISSING:
        if k in btn_map:
            result[k] = btn_map[k]
        else:
            result[k] = _v(k, EN)  # store EN as explicit value (t() fallback anyway)
    return result

TRANSLATIONS = {
    "zh-CN": {k: t2s(_v(k, TW)) for k in MISSING},
    "ko-KR": _make_lang("ko-KR"),
    **{lang: _make_lang(lang) for lang in [
        "fr-FR","de-DE","es-ES","pt-BR","it-IT","ru-RU","ar-SA",
        "hi-IN","th-TH","vi-VN","id-ID","ms-MY","tr-TR","nl-NL","pl-PL"
    ]},
}

def main():
    for lang, trans in TRANSLATIONS.items():
        path = LOCALES / f"{lang}.json"
        if not path.exists(): continue
        data = json.loads(path.read_text(encoding="utf-8"))
        written = sum(1 for k,v in trans.items()
                      if k not in data or data[k] == EN.get(k,""))
        data.update({k:v for k,v in trans.items()
                     if k not in data or data[k] == EN.get(k,"")})
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        total = sum(1 for k in data if not k.startswith("_commands."))
        print(f"  ✅ {lang}: +{written} keys  ({total}/1230 total)")

if __name__ == "__main__":
    print("AI-QMS i18n Direct Injection")
    main()
    print("Done.")
