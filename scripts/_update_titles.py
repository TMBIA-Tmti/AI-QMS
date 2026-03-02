"""One-time script: Update welcome.main.title, welcome.main.greeting,
welcome.doc_control.title, welcome.doc_control.greeting in all 20 locales."""

import json
import os

LOCDIR = os.path.join(os.path.dirname(__file__), "..", "src", "chainlit_app", "locales")

TRANSLATIONS = {
    "zh-TW": {
        "welcome.main.title": "🏥 **TMBIA-Tmti AI-QMS 品質法規助理 (Eira)**",
        "welcome.main.greeting": "您好，我是 Eira。歡迎使用本 AI 輔助系統，Eira 可協助您進行品質文件審查、醫療器材法規符合性評估，以及各國法規標準的查詢與分析。",
        "welcome.doc_control.title": "📄 **TMBIA-Tmti AI-QMS 文件管制系統 (Eira)**",
        "welcome.doc_control.greeting": "您好，我是 Eira。歡迎使用文件管制系統，Eira 可協助您進行文件上傳、OCR 辨識、版本管理、簽章偵測及稽核紀錄等品質文件管理作業。",
    },
    "zh-CN": {
        "welcome.main.title": "🏥 **TMBIA-Tmti AI-QMS 品质法规助理 (Eira)**",
        "welcome.main.greeting": "您好，我是 Eira。欢迎使用本 AI 辅助系统，Eira 可协助您进行品质文件审查、医疗器材法规符合性评估，以及各国法规标准的查询与分析。",
        "welcome.doc_control.title": "📄 **TMBIA-Tmti AI-QMS 文件管制系统 (Eira)**",
        "welcome.doc_control.greeting": "您好，我是 Eira。欢迎使用文件管制系统，Eira 可协助您进行文件上传、OCR 辨识、版本管理、签章检测及审计记录等品质文件管理作业。",
    },
    "en-US": {
        "welcome.main.title": "🏥 **TMBIA-Tmti AI-QMS Regulatory Assistant (Eira)**",
        "welcome.main.greeting": "Hello, I am Eira. Welcome to the AI-assisted quality management system. Eira can help you with quality document review, medical device regulatory compliance assessment, and regulatory standards research and analysis across jurisdictions.",
        "welcome.doc_control.title": "📄 **TMBIA-Tmti AI-QMS Document Control (Eira)**",
        "welcome.doc_control.greeting": "Hello, I am Eira. Welcome to the Document Control system. Eira can assist you with document upload, OCR processing, version management, signature detection, and audit trail operations.",
    },
    "ja-JP": {
        "welcome.main.title": "🏥 **TMBIA-Tmti AI-QMS 法規アシスタント (Eira)**",
        "welcome.main.greeting": "こんにちは、Eira です。AI 品質管理支援システムへようこそ。Eira は品質文書の審査、医療機器法規の適合性評価、各国の法規基準の照会と分析をお手伝いいたします。",
        "welcome.doc_control.title": "📄 **TMBIA-Tmti AI-QMS 文書管理システム (Eira)**",
        "welcome.doc_control.greeting": "こんにちは、Eira です。文書管理システムへようこそ。Eira はファイルのアップロード、OCR 処理、バージョン管理、署名検出、監査証跡の管理をお手伝いいたします。",
    },
    "ko-KR": {
        "welcome.main.title": "🏥 **TMBIA-Tmti AI-QMS 법규 어시스턴트 (Eira)**",
        "welcome.main.greeting": "안녕하세요, Eira입니다. AI 품질관리 지원 시스템에 오신 것을 환영합니다. Eira는 품질 문서 검토, 의료기기 법규 적합성 평가, 각국 법규 기준의 조회 및 분석을 지원합니다.",
        "welcome.doc_control.title": "📄 **TMBIA-Tmti AI-QMS 문서 관리 시스템 (Eira)**",
        "welcome.doc_control.greeting": "안녕하세요, Eira입니다. 문서 관리 시스템에 오신 것을 환영합니다. Eira는 문서 업로드, OCR 처리, 버전 관리, 서명 감지 및 감사 추적 관리를 지원합니다.",
    },
    "de-DE": {
        "welcome.main.title": "🏥 **TMBIA-Tmti AI-QMS Regulierungsassistent (Eira)**",
        "welcome.main.greeting": "Guten Tag, ich bin Eira. Willkommen im AI-gestützten Qualitätsmanagementsystem. Eira unterstützt Sie bei der Prüfung von Qualitätsdokumenten, der Bewertung der Konformität mit Medizinprodukte-Vorschriften sowie der Recherche und Analyse regulatorischer Standards.",
        "welcome.doc_control.title": "📄 **TMBIA-Tmti AI-QMS Dokumentenkontrolle (Eira)**",
        "welcome.doc_control.greeting": "Guten Tag, ich bin Eira. Willkommen im Dokumentenkontrollsystem. Eira unterstützt Sie beim Hochladen von Dokumenten, der OCR-Verarbeitung, Versionsverwaltung, Signaturerkennung und der Verwaltung von Audit-Trails.",
    },
    "fr-FR": {
        "welcome.main.title": "🏥 **TMBIA-Tmti AI-QMS Assistant Réglementaire (Eira)**",
        "welcome.main.greeting": "Bonjour, je suis Eira. Bienvenue dans le système d'assistance qualité par IA. Eira peut vous aider dans la revue des documents qualité, l'évaluation de la conformité réglementaire des dispositifs médicaux, ainsi que la recherche et l'analyse des normes réglementaires.",
        "welcome.doc_control.title": "📄 **TMBIA-Tmti AI-QMS Contrôle Documentaire (Eira)**",
        "welcome.doc_control.greeting": "Bonjour, je suis Eira. Bienvenue dans le système de contrôle documentaire. Eira peut vous assister dans le téléversement de documents, le traitement OCR, la gestion des versions, la détection des signatures et la gestion des pistes d'audit.",
    },
    "es-ES": {
        "welcome.main.title": "🏥 **TMBIA-Tmti AI-QMS Asistente Regulatorio (Eira)**",
        "welcome.main.greeting": "Hola, soy Eira. Bienvenido al sistema de gestión de calidad asistido por IA. Eira puede ayudarle con la revisión de documentos de calidad, la evaluación del cumplimiento regulatorio de dispositivos médicos y la consulta y análisis de normas regulatorias.",
        "welcome.doc_control.title": "📄 **TMBIA-Tmti AI-QMS Control de Documentos (Eira)**",
        "welcome.doc_control.greeting": "Hola, soy Eira. Bienvenido al sistema de control de documentos. Eira puede asistirle con la carga de documentos, procesamiento OCR, gestión de versiones, detección de firmas y gestión de registros de auditoría.",
    },
    "pt-BR": {
        "welcome.main.title": "🏥 **TMBIA-Tmti AI-QMS Assistente Regulatório (Eira)**",
        "welcome.main.greeting": "Olá, sou a Eira. Bem-vindo ao sistema de gestão de qualidade assistido por IA. A Eira pode ajudá-lo na revisão de documentos de qualidade, avaliação de conformidade regulatória de dispositivos médicos e pesquisa e análise de normas regulatórias.",
        "welcome.doc_control.title": "📄 **TMBIA-Tmti AI-QMS Controle de Documentos (Eira)**",
        "welcome.doc_control.greeting": "Olá, sou a Eira. Bem-vindo ao sistema de controle de documentos. A Eira pode auxiliá-lo no upload de documentos, processamento OCR, gestão de versões, detecção de assinaturas e gestão de trilhas de auditoria.",
    },
    "it-IT": {
        "welcome.main.title": "🏥 **TMBIA-Tmti AI-QMS Assistente Normativo (Eira)**",
        "welcome.main.greeting": "Buongiorno, sono Eira. Benvenuto nel sistema di gestione qualità assistito da IA. Eira può assisterla nella revisione dei documenti di qualità, nella valutazione della conformità normativa dei dispositivi medici e nella ricerca e analisi degli standard normativi.",
        "welcome.doc_control.title": "📄 **TMBIA-Tmti AI-QMS Controllo Documenti (Eira)**",
        "welcome.doc_control.greeting": "Buongiorno, sono Eira. Benvenuto nel sistema di controllo documenti. Eira può assisterla nel caricamento dei documenti, nell'elaborazione OCR, nella gestione delle versioni, nel rilevamento delle firme e nella gestione delle tracce di audit.",
    },
    "nl-NL": {
        "welcome.main.title": "🏥 **TMBIA-Tmti AI-QMS Regelgevingsassistent (Eira)**",
        "welcome.main.greeting": "Hallo, ik ben Eira. Welkom bij het AI-ondersteunde kwaliteitsmanagementsysteem. Eira kan u helpen bij de beoordeling van kwaliteitsdocumenten, de evaluatie van de naleving van regelgeving voor medische hulpmiddelen en het onderzoek en de analyse van regelgevingsnormen.",
        "welcome.doc_control.title": "📄 **TMBIA-Tmti AI-QMS Documentbeheer (Eira)**",
        "welcome.doc_control.greeting": "Hallo, ik ben Eira. Welkom bij het documentbeheersysteem. Eira kan u helpen bij het uploaden van documenten, OCR-verwerking, versiebeheer, handtekeningdetectie en het beheer van audittrails.",
    },
    "pl-PL": {
        "welcome.main.title": "🏥 **TMBIA-Tmti AI-QMS Asystent Regulacyjny (Eira)**",
        "welcome.main.greeting": "Dzień dobry, jestem Eira. Witamy w systemie zarządzania jakością wspomaganym przez AI. Eira może pomóc w przeglądzie dokumentów jakościowych, ocenie zgodności z przepisami dotyczącymi wyrobów medycznych oraz wyszukiwaniu i analizie norm regulacyjnych.",
        "welcome.doc_control.title": "📄 **TMBIA-Tmti AI-QMS Kontrola Dokumentów (Eira)**",
        "welcome.doc_control.greeting": "Dzień dobry, jestem Eira. Witamy w systemie kontroli dokumentów. Eira może pomóc w przesyłaniu dokumentów, przetwarzaniu OCR, zarządzaniu wersjami, wykrywaniu podpisów i zarządzaniu śladami audytowymi.",
    },
    "ru-RU": {
        "welcome.main.title": "🏥 **TMBIA-Tmti AI-QMS Регуляторный Ассистент (Eira)**",
        "welcome.main.greeting": "Здравствуйте, я Eira. Добро пожаловать в систему управления качеством на базе ИИ. Eira поможет вам в проверке документов качества, оценке соответствия нормативным требованиям для медицинских изделий, а также в поиске и анализе регуляторных стандартов.",
        "welcome.doc_control.title": "📄 **TMBIA-Tmti AI-QMS Управление Документами (Eira)**",
        "welcome.doc_control.greeting": "Здравствуйте, я Eira. Добро пожаловать в систему управления документами. Eira поможет вам с загрузкой документов, обработкой OCR, управлением версиями, обнаружением подписей и управлением аудиторскими записями.",
    },
    "tr-TR": {
        "welcome.main.title": "🏥 **TMBIA-Tmti AI-QMS Mevzuat Asistanı (Eira)**",
        "welcome.main.greeting": "Merhaba, ben Eira. Yapay zeka destekli kalite yönetim sistemine hoş geldiniz. Eira, kalite belgelerinin incelenmesi, tıbbi cihaz mevzuatına uygunluk değerlendirmesi ve düzenleyici standartların araştırılması ve analizinde size yardımcı olabilir.",
        "welcome.doc_control.title": "📄 **TMBIA-Tmti AI-QMS Doküman Kontrol (Eira)**",
        "welcome.doc_control.greeting": "Merhaba, ben Eira. Doküman kontrol sistemine hoş geldiniz. Eira, belge yükleme, OCR işleme, versiyon yönetimi, imza tespiti ve denetim izi yönetiminde size yardımcı olabilir.",
    },
    "ar-SA": {
        "welcome.main.title": "🏥 **TMBIA-Tmti AI-QMS مساعد التنظيم (Eira)**",
        "welcome.main.greeting": "مرحباً، أنا Eira. أهلاً بكم في نظام إدارة الجودة المدعوم بالذكاء الاصطناعي. يمكن لـ Eira مساعدتكم في مراجعة وثائق الجودة وتقييم الامتثال التنظيمي للأجهزة الطبية والبحث والتحليل في المعايير التنظيمية.",
        "welcome.doc_control.title": "📄 **TMBIA-Tmti AI-QMS التحكم في الوثائق (Eira)**",
        "welcome.doc_control.greeting": "مرحباً، أنا Eira. أهلاً بكم في نظام التحكم في الوثائق. يمكن لـ Eira مساعدتكم في رفع الوثائق ومعالجة OCR وإدارة الإصدارات وكشف التوقيعات وإدارة مسارات التدقيق.",
    },
    "hi-IN": {
        "welcome.main.title": "🏥 **TMBIA-Tmti AI-QMS नियामक सहायक (Eira)**",
        "welcome.main.greeting": "नमस्कार, मैं Eira हूँ। AI-सहायता प्राप्त गुणवत्ता प्रबंधन प्रणाली में आपका स्वागत है। Eira गुणवत्ता दस्तावेजों की समीक्षा, चिकित्सा उपकरण नियामक अनुपालन मूल्यांकन और नियामक मानकों के अनुसंधान एवं विश्लेषण में आपकी सहायता कर सकती है।",
        "welcome.doc_control.title": "📄 **TMBIA-Tmti AI-QMS दस्तावेज़ नियंत्रण (Eira)**",
        "welcome.doc_control.greeting": "नमस्कार, मैं Eira हूँ। दस्तावेज़ नियंत्रण प्रणाली में आपका स्वागत है। Eira दस्तावेज़ अपलोड, OCR प्रसंस्करण, संस्करण प्रबंधन, हस्ताक्षर पहचान और ऑडिट ट्रेल प्रबंधन में आपकी सहायता कर सकती है।",
    },
    "th-TH": {
        "welcome.main.title": "🏥 **TMBIA-Tmti AI-QMS ผู้ช่วยด้านกฎระเบียบ (Eira)**",
        "welcome.main.greeting": "สวัสดีค่ะ ดิฉัน Eira ยินดีต้อนรับสู่ระบบบริหารคุณภาพที่ขับเคลื่อนด้วย AI Eira สามารถช่วยคุณในการตรวจสอบเอกสารคุณภาพ การประเมินความสอดคล้องของกฎระเบียบเครื่องมือแพทย์ และการค้นคว้าวิเคราะห์มาตรฐานกฎระเบียบต่างๆ",
        "welcome.doc_control.title": "📄 **TMBIA-Tmti AI-QMS ระบบควบคุมเอกสาร (Eira)**",
        "welcome.doc_control.greeting": "สวัสดีค่ะ ดิฉัน Eira ยินดีต้อนรับสู่ระบบควบคุมเอกสาร Eira สามารถช่วยคุณในการอัปโหลดเอกสาร การประมวลผล OCR การจัดการเวอร์ชัน การตรวจจับลายเซ็น และการจัดการเส้นทางการตรวจสอบ",
    },
    "vi-VN": {
        "welcome.main.title": "🏥 **TMBIA-Tmti AI-QMS Trợ lý Pháp quy (Eira)**",
        "welcome.main.greeting": "Xin chào, tôi là Eira. Chào mừng bạn đến với hệ thống quản lý chất lượng hỗ trợ bởi AI. Eira có thể hỗ trợ bạn rà soát tài liệu chất lượng, đánh giá tuân thủ quy định thiết bị y tế, cũng như tra cứu và phân tích các tiêu chuẩn pháp quy.",
        "welcome.doc_control.title": "📄 **TMBIA-Tmti AI-QMS Quản lý Tài liệu (Eira)**",
        "welcome.doc_control.greeting": "Xin chào, tôi là Eira. Chào mừng bạn đến với hệ thống quản lý tài liệu. Eira có thể hỗ trợ bạn tải lên tài liệu, xử lý OCR, quản lý phiên bản, phát hiện chữ ký và quản lý dấu vết kiểm toán.",
    },
    "id-ID": {
        "welcome.main.title": "🏥 **TMBIA-Tmti AI-QMS Asisten Regulasi (Eira)**",
        "welcome.main.greeting": "Halo, saya Eira. Selamat datang di sistem manajemen mutu berbasis AI. Eira dapat membantu Anda dalam tinjauan dokumen mutu, penilaian kepatuhan regulasi perangkat medis, serta pencarian dan analisis standar regulasi.",
        "welcome.doc_control.title": "📄 **TMBIA-Tmti AI-QMS Pengendalian Dokumen (Eira)**",
        "welcome.doc_control.greeting": "Halo, saya Eira. Selamat datang di sistem pengendalian dokumen. Eira dapat membantu Anda dalam pengunggahan dokumen, pemrosesan OCR, manajemen versi, deteksi tanda tangan, dan pengelolaan jejak audit.",
    },
    "ms-MY": {
        "welcome.main.title": "🏥 **TMBIA-Tmti AI-QMS Pembantu Regulatori (Eira)**",
        "welcome.main.greeting": "Hai, saya Eira. Selamat datang ke sistem pengurusan kualiti berasaskan AI. Eira boleh membantu anda dalam semakan dokumen kualiti, penilaian pematuhan regulatori peranti perubatan, serta penyelidikan dan analisis standard regulatori.",
        "welcome.doc_control.title": "📄 **TMBIA-Tmti AI-QMS Kawalan Dokumen (Eira)**",
        "welcome.doc_control.greeting": "Hai, saya Eira. Selamat datang ke sistem kawalan dokumen. Eira boleh membantu anda dalam muat naik dokumen, pemprosesan OCR, pengurusan versi, pengesanan tandatangan dan pengurusan jejak audit.",
    },
}

updated = 0
for fname in sorted(os.listdir(LOCDIR)):
    if not fname.endswith(".json"):
        continue
    locale = fname.replace(".json", "")
    if locale not in TRANSLATIONS:
        continue
    fpath = os.path.join(LOCDIR, fname)
    with open(fpath, "r", encoding="utf-8") as f:
        data = json.load(f)
    for k, v in TRANSLATIONS[locale].items():
        data[k] = v
    with open(fpath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")
    updated += 1
    print(f"OK {locale}")

print(f"\nUpdated {updated}/20 locales")
