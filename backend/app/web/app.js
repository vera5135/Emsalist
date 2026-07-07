const $ = (id) => document.getElementById(id);

const FILE_API_BASES = ["http://127.0.0.1:8003", "http://127.0.0.1:8001", "http://127.0.0.1:8000"];
let activeApiBase = window.location.protocol === "file:" ? FILE_API_BASES[0] : "";
const apiUrl = (path) => `${activeApiBase}${path}`;

const els = {
  healthPill: $("healthPill"),
  caseText: $("caseText"),
  practiceArea: $("practiceArea"),
  maxResults: $("maxResults"),
  requestType: $("requestType"),
  strategyOutput: $("strategyOutput"),
  questionFields: $("questionFields"),
  statusLine: $("statusLine"),
  themeToggle: $("themeToggle"),
  analysisOutput: $("analysisOutput"),
  brainOutput: $("brainOutput"),
  decisionOutput: $("decisionOutput"),
  draftOutput: $("draftOutput"),
  petitionReadinessNotice: $("petitionReadinessNotice"),
  riskOutput: $("riskOutput"),
  strategyTabOutput: $("strategyTabOutput"),
  legalIssueGraphOutput: $("legalIssueGraphOutput"),
  clientQuestionsOutput: $("clientQuestionsOutput"),
  defenseOutput: $("defenseOutput"),
  officialSourcesOutput: $("officialSourcesOutput"),
  documentFiles: $("documentFiles"),
  documentType: $("documentType"),
  documentApproval: $("documentApproval"),
  documentOutput: $("documentOutput"),
  documentCount: $("documentCount"),
  documentGroundingState: $("documentGroundingState"),
  documentSelectionState: $("documentSelectionState"),
  evidenceOutput: $("evidenceOutput"),
  evidenceCount: $("evidenceCount"),
  draftReadinessDialog: $("draftReadinessDialog"),
  draftReadinessIssues: $("draftReadinessIssues"),
  analysisCount: $("analysisCount"),
  brainCount: $("brainCount"),
  decisionCount: $("decisionCount"),
  riskCount: $("riskCount"),
  strategyCount: $("strategyCount"),
  defenseCount: $("defenseCount"),
  officialSourceCount: $("officialSourceCount"),
  buttons: [
    $("reviewBtn"),
    $("aiEnrichBtn"),
    $("aiQuestionsBtn"),
    $("aiSearchBtn"),
    $("analyzeBtn"),
    $("brainBtn"),
    $("auditSourcesBtn"),
    $("yargitayBtn"),
    $("auditPrecedentsBtn"),
    $("draftBtn"),
    $("localDraftBtn"),
    $("aiDraftBtn"),
    $("auditDraftBtn"),
    $("refineDraftBtn"),
    $("sampleBtn"),
    $("questionsBtn"),
    $("clearBtn"),
    $("copyDraftBtn"),
    $("printDraftBtn"),
    $("downloadDraftBtn"),
    $("downloadDocxBtn"),
    $("downloadPdfBtn"),
    $("downloadUdfBtn"),
    $("copyClientQuestionsBtn"),
    $("uploadDocumentsBtn"),
    $("analyzeDocumentsBtn"),
    $("confirmPreliminaryDraftBtn"),
    $("legalMapRebuildBtn"),
    $("legalMapValidateBtn"),
    $("legalMapMissingBtn"),
    $("legalMapAddNodeBtn"),
  ].filter(Boolean),
  legalMapSummary: $("legalMapSummary"),
  legalMapIssues: $("legalMapIssues"),
  legalMapGraphData: $("legalMapGraphData"),
  legalMapMissingOutput: $("legalMapMissingOutput"),
  legalMapNodeEditor: $("legalMapNodeEditor"),
  legalMapNodeType: $("legalMapNodeType"),
  legalMapNodeStatus: $("legalMapNodeStatus"),
  legalMapNodeTitle: $("legalMapNodeTitle"),
};

let lastDecisions = [];
let lastBrainResults = [];
let activeCaseId = null;
let lastCaseEnrichment = null;
let lastBetterSearches = null;
let lastStrategy = null;
let lastStrategyCase = "";
let lastStrategyRequest = "";
let questionFlow = {
  questions: [],
  currentIndex: 0,
  answers: {},
  skipped: new Set(),
  showAll: false,
};
let lastDraftData = null;
let lastDraftAudit = null;
let lastSourceAudit = null;
let lastPrecedentAudit = null;
let lastYargitaySearch = null;
let lastDocuments = [];
let lastDocumentAnalysis = null;
let lastCaseState = null;
let lastLegalIssueGraph = null;
let lastLegalMapGraph = null;
let lastLegalMapValidation = null;
/** @type {File[]} Gerçek File objelerini saklar, plain object değil. */
let selectedDocumentFiles = [];
let uiBusy = false;
let reviewWorkflowComplete = false;
let pendingPreliminaryDraftOptions = null;

const DEFAULT_MAX_RESULTS = "5";
const DEFAULT_REQUEST_TYPE = "Talebimizin kabul\u00fc";
const DEFAULT_ACTIVE_CASE_LOADING_LABEL = "Aktif Dosya: haz\u0131rlan\u0131yor";
const DEFAULT_ACTIVE_CASE_EMPTY_LABEL = "Aktif Dosya: bilinmiyor";
const DEFAULT_NEW_CASE_LABEL = "Yeni Dosya Ba\u015flat";
const DEFAULT_NEW_CASE_STATUS = "Yeni dosya ba\u015flat\u0131ld\u0131.";
const DEFAULT_ANALYSIS_EMPTY = "Hen\u00fcz analiz yok.";
const DEFAULT_BRAIN_EMPTY = "Hen\u00fcz kaynak sonucu yok.";
const DEFAULT_DECISION_EMPTY = "Hen\u00fcz emsal aramas\u0131 yap\u0131lmad\u0131.";
const DEFAULT_RISK_EMPTY = "Hen\u00fcz risk de\u011ferlendirmesi yok.";
const DEFAULT_STRATEGY_EMPTY = "Hen\u00fcz strateji haz\u0131rlanmad\u0131.";
const DEFAULT_LEGAL_ISSUE_GRAPH_EMPTY = "Hen\u00fcz hukuki mesele haritas\u0131 yok.";
const DEFAULT_CLIENT_QUESTIONS_EMPTY = "Sorular hen\u00fcz haz\u0131rlanmad\u0131.";
const DEFAULT_DEFENSE_EMPTY = "Hen\u00fcz savunma sim\u00fclasyonu yok.";
const DEFAULT_OFFICIAL_SOURCES_EMPTY = "Hen\u00fcz resm\u00ee kaynak takibi yok.";
const DEFAULT_DOCUMENTS_EMPTY = "Hen\u00fcz dosya evrak\u0131 eklenmedi.";
const DEFAULT_DOCUMENT_GROUNDING_EMPTY = "Dilek\u00e7e i\u00e7in hen\u00fcz analiz edilmi\u015f belge yok.";
const DEFAULT_DRAFT_EMPTY = "Hen\u00fcz nihai dilek\u00e7e tasla\u011f\u0131 olu\u015fturulmad\u0131.";
const DEFAULT_EVIDENCE_EMPTY = "Hen\u00fcz analiz edilmi\u015f belge delili yok.";

const DOCUMENT_FACT_LABELS = {
  court: "Mahkeme",
  case_number: "Dosya numarası",
  parties: "Taraflar",
  document_date: "Belge tarihi",
  service_date: "Tebliğ tarihi",
  hearing_date: "Duruşma tarihi",
  deadlines: "Süre",
  sale_date: "Satış tarihi",
  sale_price: "Satış bedeli",
  vehicle_make_model: "Araç marka/model",
  vehicle_plate: "Plaka",
  vehicle_vin: "Şasi",
  notary_info: "Noterlik",
  notice_date: "İhtar tarihi",
  claim_result: "Talep sonucu",
  evidence: "Deliller",
  report_date: "Rapor tarihi",
  report_number: "Rapor numarası",
  technical_findings: "Teknik tespit",
  payment_info: "Ödeme/dekont",
  power_of_attorney_info: "Vekalet",
  risk_signals: "Risk sinyali",
};

const sampleCase = `Müvekkil, maliki olduğu konutu davalı kiracıya yazılı kira sözleşmesi ile kiraya vermiştir. Müvekkilin evlenen oğlu ve gelini için bağımsız konuta ihtiyaç doğmuştur. Müvekkilin aynı ilçe sınırlarında oturmaya elverişli başka bir konutu bulunmamaktadır. Kiracıya durum sözlü olarak bildirilmiş, ancak kiracı taşınmayı kabul etmemiştir. Kira sözleşmesi dönem sonunda sona ermiş olmasına rağmen kiracı taşınmazı kullanmaya devam etmektedir. Müvekkilin ve ailesinin gerçek, samimi ve zorunlu konut ihtiyacı bulunduğundan ihtiyaç nedeniyle tahliye davası açılması istenmektedir.`;
const THEME_STORAGE_KEY = "emsalist-theme";
const UNRELATED_ARGUMENT = "Bu kaynak somut uyuşmazlıkla doğrudan bağlantılı görünmemektedir.";
const DEFAULT_PRECEDENT_PARAGRAPH =
  "Karar, gizli ayıp, ayıp ihbarı ve seçimlik hakların değerlendirilmesi bakımından somut uyuşmazlıkla bağlantılıdır.";
const RISK_PRECEDENT_PARAGRAPH =
  "Bu karar doğrudan lehe emsal gibi sunulmamalı; davalı savunması ve somut olayın ayrılan yönleri bakımından değerlendirilmelidir.";
const CLEAN_PRECEDENT_EXPLANATION =
  "Anılan kararda, ayıplı satışta ayıbın niteliği, alıcının seçimlik hakları ve delil değerlendirmesi yönünden ilkeler ortaya konulmuştur. Bu karar, somut olayda gizli ayıp iddiası ve seçimlik hakların kullanılması bakımından emsal olarak değerlendirilebilir.";

const defectiveVehicleRequest =
  "Öncelikle sözleşmeden dönülerek satış bedelinin iadesi, aksi halde ayıp oranında bedel indirimi ve zarar kalemlerinin tahsili";

const fallbackQuestions = [
  "Tarafların sıfatı ve uyuşmazlıktaki rolleri nelerdir?",
  "Somut talep ve dava türü nedir?",
  "Talebi destekleyen belge, kayıt, tanık veya diğer deliller nelerdir?",
  "Karşı tarafın muhtemel savunması veya riskli nokta nedir?",
];

const commonAnswerOptions = ["Belge mevcut", "Bilmiyorum", "Sonra tamamlanacak"];
const laborOnlyOptions = new Set([
  "SGK hizmet dÃ¶kÃ¼mÃ¼ var",
  "Ä°ÅŸe giriÅŸ tarihi belli",
  "Ä°ÅŸten Ã§Ä±kÄ±ÅŸ tarihi belli",
  "TanÄ±kla desteklenecek",
  "Banka + elden Ã¶deme",
  "Bordro gerÃ§eÄŸi yansÄ±tmÄ±yor",
  "Emsal Ã¼cret araÅŸtÄ±rmasÄ±",
  "Fiili gÃ¶rev farklÄ±",
]);
const defectiveVehicleSafeOptions = [
  "Belge mevcut",
  "Bilmiyorum",
  "Sonra tamamlanacak",
  "Servis raporu mevcut",
  "Ekspertiz raporu mevcut",
  "Noter ihtarnamesi mevcut",
  "Mesaj yazışması mevcut",
  "TRAMER kaydı araştırılacak",
  "Bilirkişi incelemesi talep edilecek",
];

const vehicleQuestionBank = [
  {
    question: "Satıcı kim?",
    options: ["Galeri/şirket", "Gerçek kişi", "Tacir", "Bilmiyorum"],
    requiredTerms: ["satici", "galeri", "sirket", "tacir"],
  },
  {
    question: "Satış belgesi ve ödeme bilgisi nedir?",
    options: ["Noter satış sözleşmesi var", "Banka dekontu var", "Elden ödeme", "Belge yok"],
    requiredTerms: ["noter", "satis belgesi", "dekont", "odeme", "bedel"],
  },
  {
    question: "Araç bilgisi ve satış bedeli belli mi?",
    options: ["Plaka/şasi bilgisi belli", "Satış bedeli belli", "Marka-model belli", "Eksik"],
    requiredTerms: ["plaka", "sasi", "marka", "model", "bedel"],
  },
  {
    question: "Satıcı satış öncesinde nasıl beyanda bulundu?",
    options: ["Sorunsuz denildi", "Kazasız denildi", "Ağır hasarsız denildi", "İlan görüntüsü var"],
    requiredTerms: ["beyan", "sorunsuz", "kazasiz", "hasarsiz", "ilan"],
  },
  {
    question: "Arıza veya ayıp nasıl tespit edildi?",
    options: ["Servis raporu", "Ekspertiz raporu", "TRAMER kaydı", "Henüz belge yok"],
    requiredTerms: ["servis", "ekspertiz", "tramer", "rapor", "ariza"],
  },
  {
    question: "Ayıp ne zaman ortaya çıktı?",
    options: ["Teslimden kısa süre sonra", "İlk kullanımda", "Serviste öğrenildi", "Tarih belirsiz"],
    requiredTerms: ["teslim", "kisa sure", "tarih", "ortaya cikti"],
  },
  {
    question: "Satıcıya ne zaman ve nasıl bildirim yapıldı?",
    options: ["WhatsApp/SMS", "Noter ihtarı", "Telefonla bildirildi", "Henüz bildirilmedi"],
    requiredTerms: ["bildirim", "ihbar", "ihtar", "whatsapp", "sms"],
  },
  {
    question: "Talep ve masraf kalemleri nelerdir?",
    options: ["Bedel iadesi", "Bedel indirimi", "Onarım gideri", "Ekspertiz/servis masrafı"],
    requiredTerms: ["bedel iadesi", "bedel indirimi", "onarim", "masraf", "talep"],
  },
];

const optionSets = {
  eviction: [
    [["adres", "sozlesme", "sözleşme", "baslangic", "başlangıç"], ["Yazılı kira sözleşmesi var", "Başlangıç tarihi sözleşmede", "Tapu kaydı mevcut", "Adres resmi kayıtla teyitli"]],
    [["kimin", "kim için"], ["Müvekkilin kendisi", "Müvekkilin oğlu/kızı", "Yeni evli aile bireyi", "İşyeri ihtiyacı"]],
    [["gercek", "gerçek", "samimi", "zorunlu"], ["Bağımsız konut ihtiyacı", "Mevcut konut yetersiz", "Aynı bölgede uygun taşınmaz yok", "İhtiyaç sürekli"]],
    [["baska", "başka", "uygun", "tasinmaz", "taşınmaz"], ["Başka uygun taşınmaz yok", "Var ancak ihtiyaca elverişli değil", "Taşınmaz dolu/kiracı var", "Tapu kayıtları istenecek"]],
    [["ihtar", "bildirim"], ["İhtarname gönderildi", "Sözlü bildirim yapıldı", "Tebliğ tarihi var", "Henüz ihtar yok"]],
    [["sure", "süre", "tarih"], ["Dönem sonu takip edildi", "Dava süresi içinde", "Tarih kontrol edilecek", "Tebliğ tarihi belli"]],
    [["delil", "belge", "tanik", "tanık"], ["Kira sözleşmesi", "Tapu kaydı", "İhtarname", "Nüfus kaydı", "Tanık"]],
  ],
  alimony: [
    [["gelir", "gider"], ["Emekli maaşı", "Kira gideri", "Sağlık gideri", "Düzenli borç ödemesi"]],
    [["nafaka", "miktar"], ["Aylık nafaka düzenli ödeniyor", "Ödeme dekontları var", "Karar tarihi belli", "Miktar güncel değil"]],
    [["alacakli", "alacaklı", "calistigina", "çalıştığına"], ["SGK kaydı istenecek", "Sosyal medya çıktısı", "Tanık", "Banka/tapu/araç kaydı"]],
    [["sosyal", "ekonomik", "degisiklik", "değişiklik"], ["Davalının geliri arttı", "Müvekkilin geliri azaldı", "Yeni aile yükümlülüğü", "Hakkaniyet değişti"]],
    [["talep"], ["Öncelikle kaldırma", "Aksi halde indirim", "Sosyal-ekonomik araştırma", "Tedbiren değerlendirme"]],
  ],
  labor: [
    [["giris", "giriş", "cikis", "çıkış", "tarih"], ["SGK hizmet dökümü var", "İşe giriş tarihi belli", "İşten çıkış tarihi belli", "Tanıkla desteklenecek"]],
    [["ucret", "ücret", "gorev", "görev"], ["Banka + elden ödeme", "Bordro gerçeği yansıtmıyor", "Emsal ücret araştırması", "Fiili görev farklı"]],
    [["fesih"], ["Haksız fesih", "Yazılı fesih bildirimi yok", "İşveren feshi", "Haklı nedenle işçi feshi"]],
    [["alacak"], ["Kıdem", "İhbar", "Fazla mesai", "Yıllık izin", "UBGT"]],
    [["fazla", "tatil", "bayram"], ["Tanık", "Puantaj", "Vardiya kayıtları", "Giriş-çıkış kayıtları"]],
    [["arabuluculuk"], ["Anlaşamama tutanağı var", "Tutanak tarihi belli", "Tüm alacak kalemleri yazıldı", "Tutanak kontrol edilecek"]],
  ],
  enforcement: [
    [["dosya", "takip", "tarih", "miktar"], ["İcra dosya no belli", "Takip tarihi belli", "Ödeme emri tebliğ edildi", "Takip miktarı belli"]],
    [["dayanak", "sozlesme", "sözleşme", "fatura", "senet"], ["Sözleşme", "Fatura", "Cari hesap", "E-posta yazışmaları", "Banka dekontu"]],
    [["itiraz", "gerekce", "gerekçe"], ["Borca itiraz", "Yetkiye itiraz", "İmzaya itiraz", "Gerekçesiz itiraz"]],
    [["likit"], ["Alacak likit", "Fatura/sözleşme ile belirli", "Bilirkişi gerekebilir", "Ticari defter kaydı var"]],
    [["inkar", "tazminat"], ["İcra inkar tazminatı talep edilecek", "En az %20", "Likit alacak vurgulanacak", "Şimdilik talep yok"]],
    [["risk", "yetki", "zamana"], ["Yetki riski var", "Zamanaşımı kontrol edilecek", "Tebligat kontrol edilecek", "Arabuluculuk gerekmez"]],
  ],
  defectiveVehicle: [
    [["satici", "satıcı", "galeri", "tacir", "tuketici", "tüketici"], ["Galeri/şirket satıcı", "Gerçek kişi satıcı", "Tüketici işlemi olabilir", "Görevli mahkeme kontrol edilecek"]],
    [["marka", "model", "plaka", "sasi", "şasi", "bedel", "satis", "satış"], ["Noter satış sözleşmesi var", "Satış bedeli ödendi", "Plaka/şasi bilgisi belli", "Ödeme dekontu mevcut"]],
    [["beyan", "ekspertiz", "ilan"], ["Kazasız beyan edildi", "Ağır hasarsız beyan edildi", "Ekspertiz raporu var", "İlan görüntüsü mevcut", "Mesaj yazışmaları var"]],
    [["agir", "ağır", "kilometre", "motor", "mekanik", "onarim", "onarım", "tespit"], ["Ağır hasar kaydı çıktı", "Motor arızası tespit edildi", "Gizli onarım izi var", "Kilometre şüphesi var", "Servis raporu mevcut"]],
    [["olagan", "olağan", "gizli"], ["Olağan muayene ile anlaşılamaz", "Gizli ayıp niteliğinde", "Teslimden kısa süre sonra ortaya çıktı", "Bilirkişi ile tespit edilmeli"]],
    [["bildirim", "ihbar"], ["Ayıp öğrenilince bildirildi", "WhatsApp/SMS ile bildirildi", "Noter ihtarı gönderildi", "Bildirim tarihi belli"]],
    [["secimlik", "seçimlik", "donme", "dönme", "bedel", "onarim", "onarım"], ["Öncelikle sözleşmeden dönme", "Aksi halde bedel indirimi", "Onarım gideri talebi", "Satış bedeli iadesi"]],
    [["zarar", "masraf", "deger", "değer"], ["Satış bedeli ile ayıplı değer farkı var", "Servis/onarım gideri var", "Ekspertiz masrafı var", "Değer kaybı bilirkişiyle belirlensin"]],
    [["delil", "servis", "hasar", "rapor", "yazisma", "yazışma", "tanik", "tanık"], ["Servis raporu", "Ekspertiz raporu", "TRAMER/hasar kaydı", "İlan ve yazışmalar", "Tanık"]],
  ],
  generic: [
    [["taraf", "rol"], ["Davacı alacaklı", "Davacı kiraya veren", "Davacı işçi", "Davalı borçlu"]],
    [["talep", "dava"], ["Asıl talep", "Terditli talep", "Tedbir talebi", "Yargılama gideri"]],
    [["delil", "belge", "kayıt", "tanik", "tanık"], ["Belge var", "Tanık var", "Resmi kayıt istenecek", "Bilirkişi gerekir"]],
    [["savunma", "risk"], ["Zamanaşımı savunması", "Yetki/görev itirazı", "İspat riski", "Karşı delil bekleniyor"]],
  ],
};

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function plainText(value) {
  return String(value ?? "")
    .toLocaleLowerCase("tr-TR")
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .replaceAll("ı", "i")
    .replaceAll("ı", "i")
    .replaceAll("ğ", "g")
    .replaceAll("ü", "u")
    .replaceAll("ş", "s")
    .replaceAll("ö", "o")
    .replaceAll("ç", "c")
    .replaceAll("ı", "i")
    .replaceAll("ğ", "g")
    .replaceAll("ü", "u")
    .replaceAll("Ş", "s")
    .replaceAll("Ö", "o")
    .replaceAll("Ç", "c")
    .replaceAll("İ", "i")
    .replaceAll("Ğ", "g")
    .replaceAll("Ü", "u");
}

function currentProfileKey() {
  const text = plainText(`${lastStrategy?.petition_type || ""} ${getRequestType()} ${getCaseText()}`);
  if (text.includes("tahliye") || text.includes("kiralanan") || text.includes("kiraci")) return "eviction";
  if (text.includes("nafaka")) return "alimony";
  if (text.includes("iscilik") || text.includes("kidem") || text.includes("ihbar") || text.includes("fazla mesai")) return "labor";
  if (text.includes("icra") || text.includes("itiraz") || text.includes("takip")) return "enforcement";
  if (text.includes("ayip") || text.includes("arac") || text.includes("ekspertiz") || text.includes("tramer")) return "defectiveVehicle";
  return "generic";
}

function vehicleContextActive() {
  const text = plainText(`${lastStrategy?.petition_type || ""} ${getRequestType()} ${getCaseText()}`);
  return [
    "arac",
    "ikinci el",
    "plaka",
    "sasi",
    "motor arizasi",
    "gizli ayip",
    "tramer",
    "ekspertiz",
    "noter satis",
    "ayipli mal",
    "volkswagen",
    "satis bedeli",
  ].some((term) => text.includes(term));
}

function sanitizeAnswerOptions(options) {
  const seen = new Set();
  const incoming = (options || []).reduce((acc, option) => {
    const value = cleanOutputText(option);
    const key = plainText(value);
    if (!value || seen.has(key)) return acc;
    seen.add(key);
    acc.push(value);
    return acc;
  }, []);
  if (!vehicleContextActive()) return incoming;
  const filtered = incoming.filter((option) => !laborOnlyOptions.has(option));
  return filtered.length ? filtered : defectiveVehicleSafeOptions.slice(0, 5);
}

function questionOptions(question) {
  const normalizedQuestion = plainText(question);
  if (currentProfileKey() === "defectiveVehicle" || vehicleContextActive()) {
    const direct = vehicleQuestionBank.find((item) => plainText(item.question) === normalizedQuestion);
    if (direct) return sanitizeAnswerOptions(direct.options).slice(0, 5);
    const matchedVehicle = vehicleQuestionBank.find((item) =>
      item.requiredTerms.some((term) => normalizedQuestion.includes(term) || plainText(item.question).includes(normalizedQuestion)),
    );
    if (matchedVehicle) return sanitizeAnswerOptions(matchedVehicle.options).slice(0, 5);
    return defectiveVehicleSafeOptions.slice(0, 5);
  }
  const profileKey = currentProfileKey();
  const profileOptions = optionSets[profileKey] || [];
  const matched = [];

  for (const [needles, options] of profileOptions) {
    if (needles.some((needle) => normalizedQuestion.includes(plainText(needle)))) {
      matched.push(...options);
    }
  }

  if (!matched.length) matched.push(...commonAnswerOptions);
  return sanitizeAnswerOptions(matched).slice(0, 5);
}

function appendAnswerOption(field, value) {
  const current = field.value.trim();
  if (!current) {
    field.value = value;
  } else if (!current.split(";").map((item) => item.trim()).includes(value)) {
    field.value = `${current}; ${value}`;
  }
  field.dispatchEvent(new Event("input", { bubbles: true }));
}

function setFieldValue(field, value) {
  field.value = value;
  field.dispatchEvent(new Event("input", { bubbles: true }));
}

function setBusy(isBusy, message) {
  uiBusy = isBusy;
  els.buttons.forEach((button) => {
    button.disabled = isBusy;
  });
  renderDocumentControls();
  if (message !== undefined) {
    setStatus(message);
  }
}

function setStatus(message, isError = false) {
  els.statusLine.textContent = message;
  els.statusLine.classList.toggle("error", isError);
}

function ensureCaseControls() {
  const nav = document.querySelector(".top-actions");
  if (!nav) return;
  if (!document.getElementById("activeCaseBadge")) {
    const badge = document.createElement("span");
    badge.id = "activeCaseBadge";
    badge.className = "status-pill";
    badge.textContent = "Aktif Dosya: hazÄ±rlanÄ±yor";
    nav.insertBefore(badge, els.healthPill || null);
  }
  if (!document.getElementById("newCaseBtn")) {
    const button = document.createElement("button");
    button.id = "newCaseBtn";
    button.type = "button";
    button.className = "ghost-btn";
    button.textContent = "Yeni Dosya BaÅŸlat";
    nav.insertBefore(button, els.healthPill || null);
  }
}

function renderActiveCaseBadge() {
  const badge = document.getElementById("activeCaseBadge");
  if (!badge) return;
  badge.textContent = activeCaseId ? `Aktif Dosya: ${activeCaseId}` : "Aktif Dosya: bilinmiyor";
}

async function initializeCaseSession() {
  const current = await apiFetch("/case/current");
  if (!current.ok) throw new Error("Aktif dosya bilgisi alÄ±namadÄ±.");
  const data = await current.json();
  activeCaseId = data.case_id || null;
  renderActiveCaseBadge();
}

function setCaseState(state) {
  lastCaseState = state && typeof state === "object" ? state : null;
  window.lastCaseState = lastCaseState || {};
}

function applyTheme(theme) {
  const nextTheme = theme === "dark" ? "dark" : "light";
  document.documentElement.dataset.theme = nextTheme;
  if (els.themeToggle) {
    els.themeToggle.checked = nextTheme === "dark";
  }
  localStorage.setItem(THEME_STORAGE_KEY, nextTheme);
}

function initTheme() {
  const storedTheme = localStorage.getItem(THEME_STORAGE_KEY);
  applyTheme(storedTheme === "dark" ? "dark" : "light");
}

function switchTab(tabName) {
  document.querySelectorAll("[data-tab]").forEach((button) => {
    button.classList.toggle("active", button.dataset.tab === tabName);
  });
  document.querySelectorAll("[data-tab-panel]").forEach((panel) => {
    panel.classList.toggle("active", panel.dataset.tabPanel === tabName);
  });
  if (tabName === "strategy" || tabName === "risks") {
    fetchLegalIssueGraph();
  }
  if (tabName === "legalmap") {
    fetchLegalMap();
  }
}

function cleanOutputText(value, fallback = "") {
  const text = String(value ?? "").replaceAll("{paragraph}", "").replaceAll("{{paragraph}}", "").trim();
  return text || fallback;
}

function renderListItems(values, fallback = "") {
  const items = (Array.isArray(values) ? values : [])
    .map((value) => String(value ?? "").trim())
    .filter(Boolean)
    .map((value) => `<li>${escapeHtml(value)}</li>`);
  if (items.length) {
    return `<ul class="compact-list">${items.join("")}</ul>`;
  }
  return fallback ? `<span>${escapeHtml(fallback)}</span>` : "";
}

function currentCaseState(source = null) {
  const candidate = source?.case_state || source || lastCaseState;
  return candidate && typeof candidate === "object" ? candidate : {};
}

function caseStatePlanItems(caseState, key) {
  const graph = caseState?.legal_issue_graph || lastLegalIssueGraph;
  if (graph && Array.isArray(graph.issues)) {
    if (key === "drafting_plan") return Array.isArray(graph.drafting_plan) ? graph.drafting_plan : [];
    if (key === "question_plan") {
      return graph.issues.flatMap((issue) => (issue.client_questions || []).map((question) => ({
        question,
        reason: issue.risk_reason || `${issue.title || "Hukuki mesele"} başlığını netleştirmek için sorulur.`,
        related_issue_key: issue.issue_id || "",
        answer_options: ["Evet", "Hayır", "Bilinmiyor"],
      })));
    }
    if (key === "evidence_plan") {
      const evidence = new Map();
      graph.issues.forEach((issue) => {
        [...(issue.available_evidence || []), ...(issue.missing_evidence || [])].forEach((title) => {
          const current = evidence.get(title) || {
            title,
            proves: [],
            status: (issue.available_evidence || []).includes(title) ? "available" : "missing",
            risk_if_missing: issue.risk_reason || "",
          };
          if (issue.issue_id && !current.proves.includes(issue.issue_id)) current.proves.push(issue.issue_id);
          evidence.set(title, current);
        });
      });
      return [...evidence.values()];
    }
    if (key === "risk_plan") {
      return graph.issues
        .filter((issue) => ["high", "medium"].includes(issue.risk_level))
        .map((issue) => ({
          title: issue.title,
          level: issue.risk_level,
          reason: issue.risk_reason,
          related_issue_keys: [issue.issue_id],
          needed_evidence: issue.missing_evidence || [],
        }));
    }
  }
  return Array.isArray(caseState?.[key]) ? caseState[key] : [];
}

function caseStateIssueTitles(caseState) {
  const graph = caseState?.legal_issue_graph || lastLegalIssueGraph;
  if (graph && Array.isArray(graph.issues)) {
    return graph.issues.map((item) => item?.title || "").filter(Boolean);
  }
  return (Array.isArray(caseState?.legal_issues) ? caseState.legal_issues : [])
    .map((item) => (typeof item === "string" ? item : item?.title || ""))
    .filter(Boolean);
}

function documentTypesForCaseState() {
  return (lastDocumentAnalysis?.documents || [])
    .map((item) => item.document_type)
    .filter(Boolean);
}

async function refreshCaseState() {
  const caseText = getCaseText();
  if (caseText.length < 10) {
    setCaseState(null);
    return null;
  }
  const analysisContext = {
    area: getRequestType(),
    case_type: lastCaseEnrichment?.detected_case_type || currentProfileKey(),
    documents: documentTypesForCaseState().map((documentType) => ({ document_type: documentType })),
    warnings: dedupeIssues([
      ...(lastCaseEnrichment?.risk_flags || []),
      ...(lastDocumentAnalysis?.warnings || []),
    ]).slice(0, 50),
  };
  const data = await apiPost("/case/state", {
    event_text: caseText,
    area: getRequestType(),
    case_type: lastCaseEnrichment?.detected_case_type || currentProfileKey(),
    document_facts: documentFactPayload().map((fact) => `${fact.fact_key}: ${fact.fact_value}`),
    question_answers: buildAnswers(),
    legal_sources: lastStrategy?.legal_basis || [],
    precedent_candidates: lastDecisions,
    drafting_package: lastDraftData?.case_state?.drafting_package || {},
    analysis_context: analysisContext,
  });
  setCaseState(data);
  return data;
}

function getCaseText() {
  return els.caseText.value.trim();
}

function getRequestType() {
  return els.requestType.value.trim() || "Talebimizin kabulü";
}

function requestIsGeneric() {
  const value = plainText(els.requestType.value);
  return !value || value === "talebimizin kabulu";
}

function applyProfileRequestDefault(strategy) {
  const profileText = plainText([strategy?.petition_type, ...(strategy?.legal_basis || [])].join(" "));
  const looksLikeDefectiveVehicle =
    profileText.includes("ayipli arac") ||
    profileText.includes("gizli ayip") ||
    profileText.includes("tbk 219") ||
    currentProfileKey() === "defectiveVehicle";
  if (looksLikeDefectiveVehicle && requestIsGeneric()) {
    setFieldValue(els.requestType, defectiveVehicleRequest);
  }
}

function getMaxResults() {
  const value = Number.parseInt(els.maxResults.value, 10);
  return Number.isFinite(value) ? Math.min(Math.max(value, 1), 20) : 5;
}

function getPracticeArea() {
  return els.practiceArea.value.trim() || null;
}

function assertCaseText() {
  const caseText = getCaseText();
  if (caseText.length < 10) {
    throw new Error("Olay veya hukuki konu en az 10 karakter olmalı.");
  }
  return caseText;
}

function withCaseId(payload = {}) {
  if (!payload || typeof payload !== "object" || Array.isArray(payload)) return payload;
  if ("case_id" in payload) return payload;
  return activeCaseId ? { ...payload, case_id: activeCaseId } : payload;
}

function caseQuery(path) {
  if (!activeCaseId) return path;
  const separator = path.includes("?") ? "&" : "?";
  return `${path}${separator}case_id=${encodeURIComponent(activeCaseId)}`;
}

async function apiFetch(path, options = {}) {
  if (window.location.protocol !== "file:") {
    return fetch(path, options);
  }

  const bases = [...new Set([activeApiBase, ...FILE_API_BASES].filter(Boolean))];
  let lastError = null;
  for (const base of bases) {
    try {
      const response = await fetch(`${base}${path}`, options);
      activeApiBase = base;
      updateApiLinks();
      return response;
    } catch (error) {
      lastError = error;
    }
  }
  throw lastError || new Error("API bağlantısı kurulamadı.");
}

async function apiPost(path, payload) {
  const response = await apiFetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(withCaseId(payload)),
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = Array.isArray(data.detail)
      ? data.detail.map((item) => item.msg || JSON.stringify(item)).join("; ")
      : data.detail || response.statusText;
    throw new Error(detail);
  }
  return data;
}

async function apiUpload(path, formData) {
  if (activeCaseId && !formData.has("case_id")) {
    formData.append("case_id", activeCaseId);
  }
  const response = await apiFetch(path, { method: "POST", body: formData });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = Array.isArray(data.detail)
      ? data.detail.map((item) => item.msg || JSON.stringify(item)).join("; ")
      : data.detail || response.statusText;
    throw new Error(detail);
  }
  return data;
}

function renderDocumentControls() {
  if (!els.documentFiles) return;
  $("uploadDocumentsBtn").disabled = uiBusy || selectedDocumentFiles.length === 0;
  $("analyzeDocumentsBtn").disabled = uiBusy || lastDocuments.length === 0;
  updateFinalPetitionReadiness();
}

function finalPetitionReadinessIssues() {
  const issues = [];
  if (!lastDocuments.length) issues.push("Belge yüklenmedi.");
  else if (!lastDocumentAnalysis) issues.push("Belge analizi henüz yapılmadı.");
  if (!reviewWorkflowComplete) issues.push("Kaynak, emsal, delil veya risk incelemesi henüz tamamlanmadı.");
  if (questionAnswerCount() === 0) issues.push("Dilekçe soruları henüz cevaplanmadı.");
  return issues;
}

function updateFinalPetitionReadiness() {
  if (!els.petitionReadinessNotice) return;
  const issues = finalPetitionReadinessIssues();
  els.petitionReadinessNotice.className = `petition-readiness ${issues.length ? "warning" : "ready"}`;
  els.petitionReadinessNotice.textContent = issues.length
    ? "Bazı eksik veya riskli hususlar tespit edildi. Taslak yine de hazırlanabilir; eksikler dilekçede ihtiyatlı dille işlenecektir."
    : "Dosya verileri güncel görünüyor. Dilekçe taslağını hazırlayabilirsiniz.";
}

function renderDocumentSelection() {
  const names = selectedDocumentFiles.map((file) => {
    if (file instanceof File) {
      return `${file.name} (${(file.size / 1024).toFixed(1)} KB)`;
    }
    return String(file.name || file);
  });
  els.documentSelectionState.className = `document-selection-state${names.length ? " pending" : ""}`;
  els.documentSelectionState.textContent = names.length
    ? `${names.length} dosya seçildi, yükleme bekliyor: ${names.join(", ")}`
    : "Yükleme için dosya seçilmedi.";
  renderDocumentControls();
}

function renderDocumentEvidence() {
  const documents = lastDocumentAnalysis?.documents || [];
  const caseState = currentCaseState();
  const evidencePlan = caseStatePlanItems(caseState, "evidence_plan");
  const evidenceFacts = documents.flatMap((documentItem) =>
    (documentItem.extracted_facts || []).filter((fact) => fact.verification_status === "fact_confirmed"),
  );
  els.evidenceCount.textContent = String(evidenceFacts.length + evidencePlan.length);
  if (!documents.length && !evidencePlan.length) {
    els.evidenceOutput.className = "empty-state";
    els.evidenceOutput.textContent = "Henüz analiz edilmiş belge delili yok.";
    return;
  }
  els.evidenceOutput.className = "result-list";
  const documentCards = documents.map((documentItem) => {
      const facts = (documentItem.extracted_facts || []).filter((fact) => fact.verification_status === "fact_confirmed");
      return `
        <div class="result-item">
          <h3>${escapeHtml(documentItem.file_name)}</h3>
          <div class="meta-row">
            <span class="chip">${escapeHtml(documentItem.document_type)}</span>
            <span class="chip status-${escapeHtml(documentItem.extraction_status)}">${escapeHtml(documentItem.extraction_status)}</span>
          </div>
          ${facts.length ? `<ol class="compact-list">${facts.map((fact) => `
            <li><strong>${escapeHtml(DOCUMENT_FACT_LABELS[fact.fact_key] || fact.fact_key)}:</strong> ${escapeHtml(fact.fact_value)}<br>
            <small>Kaynak: ${escapeHtml(fact.source_file_name)}${fact.page_number ? `, s. ${escapeHtml(fact.page_number)}` : ""}; alıntı: “${escapeHtml(fact.excerpt)}”</small></li>
          `).join("")}</ol>` : "<p>Bu belgeden doğrulanmış metinsel delil çıkarılamadı.</p>"}
        </div>
      `;
    });
  const evidencePlanCards = evidencePlan.length
    ? [`
        <div class="result-item">
          <h3>Delil Plani</h3>
          <ol class="compact-list">
            ${evidencePlan.map((item) => `
              <li>
                <strong>${escapeHtml(item.title || "Delil")}</strong><br>
                <small>Neyi ispatlar: ${escapeHtml((item.proves || []).join(", ") || "Belirtilmedi")}</small><br>
                <small>Eksikse risk: ${escapeHtml(item.risk_if_missing || "Belirtilmedi")}</small>
              </li>
            `).join("")}
          </ol>
        </div>
      `]
    : [];
  els.evidenceOutput.innerHTML = [...documentCards, ...evidencePlanCards].join("");
}

function renderDocuments() {
  els.documentCount.textContent = `${lastDocuments.length} belge`;
  if (!lastDocuments.length) {
    els.documentOutput.className = "document-list empty-state";
    els.documentOutput.textContent = "Henüz dosya evrakı eklenmedi.";
    els.documentGroundingState.className = "document-grounding-state";
    els.documentGroundingState.textContent = "Dilekçe için henüz analiz edilmiş belge yok.";
    renderDocumentEvidence();
    renderDocumentControls();
    return;
  }

  els.documentOutput.className = "document-list";
  els.documentOutput.innerHTML = lastDocuments
    .map((documentItem) => {
      const status = String(documentItem.extraction_status || "failed");
      const statusClass = ["extracted", "partial", "ocr_required", "conversion_required", "unsupported", "failed"].includes(status)
        ? `status-${status}`
        : "status-failed";
      const facts = (documentItem.extracted_facts || []).slice(0, 10);
      const missing = documentItem.missing_fields || [];
      const conflicts = documentItem.conflicts || [];
      return `
        <article class="document-card">
          <div class="document-card-head">
            <div>
              <h3>${escapeHtml(documentItem.file_name)}</h3>
              <div class="meta-row">
                <span class="chip">${escapeHtml(documentItem.document_type || "diğer")}</span>
                <span class="chip ${statusClass}">${escapeHtml(status)}</span>
                <span class="chip">${escapeHtml(documentItem.file_extension || "")}</span>
              </div>
            </div>
            <button class="ghost-btn small-btn" type="button" data-delete-document="${escapeHtml(documentItem.document_id)}">Sil</button>
          </div>
          ${documentItem.extraction_warning ? `<p class="document-warning"><strong>Uyarı:</strong> ${escapeHtml(documentItem.extraction_warning)}</p>` : ""}
          ${facts.length ? `
            <ol class="document-facts">
              ${facts.map((fact) => `
                <li>
                  <strong>${escapeHtml(DOCUMENT_FACT_LABELS[fact.fact_key] || fact.fact_key)}:</strong>
                  ${escapeHtml(fact.fact_value)}
                  <small>Kaynak: ${escapeHtml(fact.source_file_name)}${fact.page_number ? `, s. ${escapeHtml(fact.page_number)}` : ""}; güven ${Math.round(Number(fact.confidence_score || 0) * 100)}% — “${escapeHtml(fact.excerpt || "")}”</small>
                </li>
              `).join("")}
            </ol>
          ` : ""}
          ${missing.length ? `<p><strong>Eksikler:</strong> ${escapeHtml(missing.map((key) => DOCUMENT_FACT_LABELS[key] || key).join(", "))}</p>` : ""}
          ${conflicts.map((conflict) => `<p class="document-conflict"><strong>Çelişki:</strong> ${escapeHtml(conflict.warning)}</p>`).join("")}
        </article>
      `;
    })
    .join("");

  if (!lastDocumentAnalysis) {
    els.documentGroundingState.className = "document-grounding-state warning";
    els.documentGroundingState.textContent = "Belgeler yüklendi. Dilekçe akışından önce Belgeleri Analiz Et adımını çalıştırın.";
    renderDocumentEvidence();
    renderDocumentControls();
    return;
  }
  const conflictCount = (lastDocumentAnalysis.conflicts || []).length;
  const warningCount = (lastDocumentAnalysis.warnings || []).length;
  els.documentGroundingState.className = `document-grounding-state ${lastDocumentAnalysis.grounding_ready ? "ready" : "warning"}`;
  els.documentGroundingState.textContent = lastDocumentAnalysis.grounding_ready
    ? `${(lastDocumentAnalysis.confirmed_facts || []).length} bilgi kaynaklandırıldı; dilekçe akışı için analizi onaylayın.`
    : `Analiz tamamlandı: ${conflictCount} çelişki, ${warningCount} okuma/OCR uyarısı. Kesin bilgi olarak yalnızca doğrulanan olgular kullanılacak.`;
  renderDocumentEvidence();
  renderDocumentControls();
}

function userClaimsFromCase() {
  const text = `${getCaseText()} ${getRequestType()}`;
  const patterns = {
    sale_price: /satış\s+bedel(?:i)?\s*[:\-]?(?:nin)?\s*((?:\d{1,3}(?:[. ]\d{3})+|\d+)(?:,\d{1,2})?\s*(?:TL|TRY|₺))/i,
    sale_date: /satış\s+tarih(?:i)?\s*[:\-]?\s*(\d{1,2}[./-]\d{1,2}[./-]\d{4})/i,
    vehicle_plate: /plaka(?:\s+numarası)?\s*[:\-]?\s*(\d{2}\s*[A-ZÇĞİÖŞÜ]{1,3}\s*\d{2,5})/i,
    vehicle_vin: /(?:şasi|şase|VIN)(?:\s+numarası)?\s*[:\-]?\s*([A-HJ-NPR-Z0-9]{17})/i,
    case_number: /(?:esas|dosya)\s*(?:no|numarası)?\s*[:\-]?\s*(\d{4}\s*\/\s*\d+)/i,
  };
  return Object.fromEntries(
    Object.entries(patterns)
      .map(([key, pattern]) => [key, text.match(pattern)?.[1]?.trim()])
      .filter(([, value]) => value),
  );
}

function documentFactPayload() {
  return (lastDocumentAnalysis?.confirmed_facts || []).filter((fact) => fact.verification_status === "fact_confirmed");
}

function documentConfirmedFactTexts() {
  return documentFactPayload().map((fact) => {
    const label = DOCUMENT_FACT_LABELS[fact.fact_key] || fact.fact_key;
    const page = fact.page_number ? `, s. ${fact.page_number}` : "";
    return `${label}: ${fact.fact_value} (Kaynak belge: ${fact.source_file_name}${page}; alıntı: ${fact.excerpt})`;
  });
}

function documentMissingFields() {
  return (lastDocumentAnalysis?.missing_fields || []).map((key) => DOCUMENT_FACT_LABELS[key] || key);
}

function documentMissingQuestions() {
  return documentMissingFields().map((label) => `Belgeden çıkarılamayan ${label} bilgisi nedir?`);
}

function prefillQuestionsFromDocuments() {
  const facts = documentFactPayload();
  if (!facts.length || !questionFlow.questions.length) return;
  const termsByFact = {
    parties: ["taraf", "satıcı", "alıcı"],
    sale_price: ["satış bedeli", "bedel"],
    sale_date: ["satış tarihi"],
    vehicle_make_model: ["marka", "model", "araç bilgisi"],
    vehicle_plate: ["plaka"],
    vehicle_vin: ["şasi", "şase"],
    evidence: ["delil"],
    claim_result: ["talep"],
    service_date: ["tebliğ"],
    hearing_date: ["duruşma"],
    payment_info: ["ödeme", "dekont"],
    technical_findings: ["arıza", "tespit", "rapor"],
  };
  questionFlow.questions.forEach((item) => {
    if (questionFlow.answers[item.question]) return;
    const question = plainText(item.question);
    const matching = facts.filter((fact) => (termsByFact[fact.fact_key] || []).some((term) => question.includes(plainText(term))));
    if (matching.length) {
      questionFlow.answers[item.question] = matching
        .map((fact) => `${fact.fact_value} (Kaynak: ${fact.source_file_name}${fact.page_number ? `, s. ${fact.page_number}` : ""})`)
        .join("; ");
    }
  });
  renderQuestionCard();
}

function assertDocumentFlowReady() {
  return true;
}

function draftReadinessIssues() {
  const issues = [];
  if (questionAnswerCount() === 0) issues.push("Dilekçe soruları henüz cevaplanmadı.");
  if (!lastDocuments.length) issues.push("Dosya evrakı yüklenmedi ve analiz edilmedi.");
  else if (!lastDocumentAnalysis) issues.push("Yüklenen dosya evrakları henüz analiz edilmedi.");
  if (!reviewWorkflowComplete) issues.push("Kaynak, emsal, delil ve risk incelemesi tamamlanmadı.");
  return issues;
}

function showDraftReadinessDialog(issues, options) {
  pendingPreliminaryDraftOptions = { ...options, preliminaryApproved: true };
  els.draftReadinessIssues.innerHTML = issues.map((issue) => `<li>${escapeHtml(issue)}</li>`).join("");
  if (!els.draftReadinessDialog.open) {
    els.draftReadinessDialog.showModal();
  }
}

async function loadDocuments() {
  const response = await apiFetch(caseQuery("/documents"));
  if (!response.ok) throw new Error("Belge listesi alınamadı.");
  lastDocuments = await response.json();
  lastDocumentAnalysis = null;
  renderDocuments();
  renderDocumentSelection();
}

async function uploadDocuments() {
  const files = [...selectedDocumentFiles];
  if (!files.length) throw new Error("Önce yüklenecek belgeyi seçin.");

  // Her dosyanın gerçek File objesi olduğunu doğrula
  for (const file of files) {
    if (!(file instanceof File)) {
      throw new Error(`Geçersiz dosya: seçilen dosya bir File objesi değil. Lütfen dosyayı tekrar seçin.`);
    }
    if (file.size <= 0) {
      throw new Error(`"${file.name}" dosyası boş. Seçilen dosya boş olamaz.`);
    }
  }

  setBusy(true, "Belgeler güvenli alana yükleniyor...");
  try {
    // "Otomatik algıla" seçiliyse document_type hiç gönderme
    const documentTypeValue = els.documentType.value;
    const shouldSendDocumentType = documentTypeValue !== "";

    let uploadedCount = 0;
    let duplicateCount = 0;
    for (const file of files) {
      const formData = new FormData();
      // Gerçek File objesini ekle - üçüncü parametre (filename) opsiyonel
      formData.append("file", file);

      if (shouldSendDocumentType) {
        formData.append("document_type", documentTypeValue);
      }
      // "Otomatik algıla" (boş değer) seçiliyken document_type hiç gönderilmez
      // Backend default=None olarak alır ve otomatik algılar

      try {
        const uploaded = await apiUpload("/documents/upload", formData);
        lastDocuments = [uploaded, ...lastDocuments.filter((item) => item.document_id !== uploaded.document_id)];
        uploadedCount += 1;
        renderDocuments();
      } catch (error) {
        if (plainText(error.message).includes("bu belge zaten ekli")) {
          duplicateCount += 1;
          continue;
        }
        throw error;
      }
    }
    if (uploadedCount) {
      lastDocumentAnalysis = null;
      reviewWorkflowComplete = false;
      els.documentApproval.checked = false;
    }
    // Upload başarılı olduktan sonra temizle
    selectedDocumentFiles = [];
    els.documentFiles.value = "";
    renderDocumentSelection();
    renderDocuments();
    if (duplicateCount && !uploadedCount) {
      setStatus("Bu belge zaten ekli.", true);
    } else if (duplicateCount) {
      setStatus(`${uploadedCount} belge yüklendi; ${duplicateCount} belge zaten ekli olduğu için atlandı.`);
    } else {
      setStatus(`${uploadedCount} belge yüklendi. Şimdi belgeleri analiz edin.`);
    }
  } finally {
    setBusy(false);
  }
}

async function analyzeDocuments() {
  if (!lastDocuments.length) throw new Error("Önce belgeyi yükleyin.");
  setBusy(true, "Belgeler okunuyor, bilgiler kaynaklandırılıyor ve çelişkiler denetleniyor...");
  try {
    const data = await apiPost("/documents/analyze", {
      document_ids: lastDocuments.map((item) => item.document_id),
      user_claims: userClaimsFromCase(),
      document_types: {},
    });
    lastDocumentAnalysis = data;
    reviewWorkflowComplete = false;
    lastDocuments = data.documents || [];
    els.documentApproval.checked = false;
    await refreshCaseState();
    renderDocuments();
    prefillQuestionsFromDocuments();
    renderRisks();
    renderStrategyToolkit();
    const conflictSuffix = data.conflicts?.length ? ` ${data.conflicts.length} çelişki doğrulama bekliyor.` : "";
    setStatus(`Belge analizi tamamlandı; ${data.confirmed_facts?.length || 0} bilgi kaynaklandırıldı.${conflictSuffix}`);
    return data;
  } finally {
    setBusy(false);
  }
}

async function deleteDocument(documentId) {
  const response = await apiFetch(caseQuery(`/documents/${encodeURIComponent(documentId)}`), { method: "DELETE" });
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    throw new Error(data.detail || "Belge silinemedi.");
  }
  lastDocuments = lastDocuments.filter((item) => item.document_id !== documentId);
  lastDocumentAnalysis = null;
  els.documentApproval.checked = false;
  renderDocuments();
  setStatus("Belge silindi. Kalan belgeler yeniden analiz edilmelidir.");
}

function renderAnalysis(data) {
  const caseState = currentCaseState(data);
  const facts = data.case_facts || [];
  const keywords = data.legal_keywords || [];
  const issues = caseStateIssueTitles(caseState);
  const risks = caseStatePlanItems(caseState, "risk_plan");
  const queries = caseState.research_queries || [];
  els.analysisCount.textContent = String(facts.length + keywords.length + issues.length + risks.length + queries.length);
  els.analysisOutput.className = "result-list";
  els.analysisOutput.innerHTML = `
    <div class="result-item">
      <h3>${escapeHtml(data.legal_topic || "Konu")}</h3>
      <div class="meta-row">
        ${keywords.map((keyword) => `<span class="chip">${escapeHtml(keyword)}</span>`).join("")}
      </div>
      <ol class="compact-list">
        ${facts.map((fact) => `<li>${escapeHtml(fact)}</li>`).join("")}
      </ol>
    </div>
    <div class="result-item">
      <h3>Hukuki Meseleler</h3>
      <ol class="compact-list">${issues.map((item) => `<li>${escapeHtml(item)}</li>`).join("") || "<li>Hukuki mesele Ã¼retilmedi.</li>"}</ol>
    </div>
    <div class="result-item">
      <h3>Kritik Riskler</h3>
      <ol class="compact-list">${risks
        .map((item) => `<li><strong>${escapeHtml(item.title || "Risk")}:</strong> ${escapeHtml(item.reason || "Sebep belirtilmedi.")}</li>`)
        .join("") || "<li>Kritik risk bulunmadÄ±.</li>"}</ol>
    </div>
    <div class="result-item">
      <h3>Arastirma Sorgulari</h3>
      <div class="meta-row">${queries.map((item) => `<span class="chip">${escapeHtml(item)}</span>`).join("") || "<span class=\"chip\">Sorgu Ã¼retilmedi</span>"}</div>
    </div>
  `;
}

function renderAIEnrichment(data) {
  lastCaseEnrichment = data;
  const missing = data.missing_facts || [];
  const questions = data.critical_questions || [];
  const queries = data.yargitay_query_templates || [];
  const keywords = data.search_keywords || [];
  els.analysisCount.textContent = String(missing.length + questions.length + keywords.length);
  els.analysisOutput.className = "result-list";
  els.analysisOutput.innerHTML = `
    <div class="result-item">
      <h3>${escapeHtml(data.detected_case_type || "AI olay analizi")}</h3>
      <div class="meta-row">
        <span class="chip blue">${data.ai_used ? "Gemini" : "Fallback"}</span>
        ${data.detected_practice_area ? `<span class="chip">${escapeHtml(data.detected_practice_area)}</span>` : ""}
        <span class="chip">${escapeHtml(data.confidence ?? 0)} güven</span>
      </div>
      <p>${escapeHtml(data.detected_practice_area || "Olay, dilekçe üretimi öncesinde arama ve kalite denetimi için yapılandırıldı.")}</p>
    </div>
    <div class="result-item">
      <h3>Eksik Bilgiler</h3>
      <ol class="compact-list">${missing.map((item) => `<li>${escapeHtml(item)}</li>`).join("") || "<li>Belirgin eksik bilgi yok.</li>"}</ol>
    </div>
    <div class="result-item">
      <h3>Kritik Sorular</h3>
      <ol class="compact-list">${questions.map((item) => `<li>${escapeHtml(item)}</li>`).join("") || "<li>Ek soru üretilmedi.</li>"}</ol>
    </div>
    <div class="result-item">
      <h3>Arama Sorguları</h3>
      <div class="meta-row">${queries.map((item) => `<span class="chip">${escapeHtml(item)}</span>`).join("")}</div>
      ${data.legal_brain_query ? `<p>${escapeHtml(data.legal_brain_query)}</p>` : ""}
    </div>
  `;
  if ((data.detected_case_type || "").toLocaleLowerCase("tr-TR").includes("araç")) {
    applyProfileRequestDefault({ petition_type: data.detected_case_type, legal_basis: data.relevant_articles || [] });
  }
}

function renderAISearch(data) {
  lastBetterSearches = data;
  els.analysisOutput.className = "result-list";
  els.analysisOutput.innerHTML = `
    <div class="result-item">
      <h3>AI Arama Sorguları</h3>
      <div class="meta-row">
        <span class="chip blue">${data.ai_used ? "Gemini" : "Fallback"}</span>
        ${(data.must_include_terms || []).map((item) => `<span class="chip">${escapeHtml(item)}</span>`).join("")}
      </div>
      <ol class="compact-list">${(data.yargitay_queries || []).map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ol>
      ${data.legal_brain_query ? `<p>${escapeHtml(data.legal_brain_query)}</p>` : ""}
    </div>
  `;
  els.analysisCount.textContent = String((data.yargitay_queries || []).length);
}

function renderDraftAudit(data) {
  const groups = [
    ["Kritik", data.critical_issues || []],
    ["Büyük", data.major_issues || []],
    ["Dil", data.petition_language_problems || []],
    ["Emsal", data.precedent_problems || []],
    ["Kaynak", data.source_problems || []],
    ["Eksik", data.missing_facts || []],
  ];
  els.analysisOutput.className = "result-list";
  els.analysisOutput.innerHTML = `
    <div class="result-item">
      <h3>Dilekçe Kalite Kontrol</h3>
      <div class="meta-row">
        <span class="chip blue">${escapeHtml(data.quality_score)} puan</span>
        <span class="chip">${data.ai_used ? "Gemini" : "Fallback"}</span>
        <span class="chip">${data.ready_for_lawyer_review ? "İncelemeye hazır" : "Düzeltme önerilir"}</span>
      </div>
      ${groups
        .filter(([, items]) => items.length)
        .map(([, items]) => `<ol class="compact-list">${items.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ol>`)
        .join("") || "<p>Kritik kalite sorunu bulunmadı.</p>"}
    </div>
  `;
  els.analysisCount.textContent = String(data.quality_score ?? 0);
  renderRisks({ draftAudit: data });
}

function renderBrain(data) {
  const results = [...(data.results || data.book_sources || [])].sort(
    (a, b) => Number(Boolean(b.is_directly_relevant)) - Number(Boolean(a.is_directly_relevant)),
  );
  lastBrainResults = results;
  const visibleResults = results.filter(
    (item) => item.is_directly_relevant !== false && cleanOutputText(item.usable_argument) !== UNRELATED_ARGUMENT,
  );
  const filteredCount = results.length - visibleResults.length;
  els.brainCount.textContent = String(visibleResults.length);
  if (!visibleResults.length) {
    const warningText = (data.warnings || []).length
      ? `<p>${escapeHtml((data.warnings || []).join(" "))}</p>`
      : "";
    els.brainOutput.className = "result-list";
    els.brainOutput.innerHTML = `
      <div class="result-item">
        <h3>Kaynak taraması</h3>
        <div class="meta-row">
          <span class="chip blue">${escapeHtml(results.length)} kaynak incelendi</span>
          <span class="chip">${escapeHtml(filteredCount)} kaynak filtrelendi</span>
        </div>
        <p>Bu dosya için doğrudan kullanılabilir Legal Brain kaynağı bulunamadı. Mevzuat ve Yargıtay emsalleri üzerinden devam edildi.</p>
        ${warningText}
      </div>
      ${filteredCount ? `<div class="result-item"><h3>Filtre sonucu</h3><p>Konu dışı kaynaklar filtrelendi.</p></div>` : ""}
    `;
    return;
  }
  els.brainOutput.className = "result-list";
  els.brainOutput.innerHTML = `
    ${filteredCount ? `<div class="result-item"><h3>Filtre sonucu</h3><p>Konu dışı kaynaklar filtrelendi.</p></div>` : ""}
    ${visibleResults
    .map((item) => {
      const title = item.title || item.section_title || "Kaynak";
      const score = item.relevance_score ?? "";
      const used = item.use_in_petition !== false && item.is_directly_relevant !== false;
      const preview =
        item.is_directly_relevant === false
          ? item.relevance_reason || UNRELATED_ARGUMENT
          : item.usable_argument || item.doctrine_principle || item.chunk_preview || "";
      const citation = item.citation_label || [item.author, item.page_start && `s. ${item.page_start}`].filter(Boolean).join(", ");
      const reason = item.relevance_reason || item.reason || (used ? "Somut uyuşmazlıkla doğrudan bağlantılı göründüğü için kullanılabilir." : "Konu dışı olduğu için elendi.");
      return `
        <div class="result-item">
          <h3>${escapeHtml(title)}</h3>
          <div class="meta-row">
            ${score !== "" ? `<span class="chip blue">${escapeHtml(score)} puan</span>` : ""}
            <span class="chip">${escapeHtml(item.source_type || item.kind || "kaynak")}</span>
            <span class="chip">${used ? "Dilekçede kullanılabilir" : "Dilekçede kullanılmadı"}</span>
            ${citation ? `<span class="chip">${escapeHtml(citation)}</span>` : ""}
          </div>
          <ol class="compact-list">
            <li><strong>Neden:</strong> ${escapeHtml(reason)}</li>
            <li><strong>Kullanılabilir argüman:</strong> ${escapeHtml(preview || "Bu kaynak için temiz argüman üretilemedi.")}</li>
            ${citation ? `<li><strong>Sayfa / tarih:</strong> ${escapeHtml(citation)}</li>` : ""}
          </ol>
        </div>
      `;
    })
    .join("")}
  `;
}

function cleanDecisionParagraph(item) {
  const alignment = plainText(`${item.lehe_aleyhe || ""} ${item.usefulness_score || ""}`);
  const risk = alignment.includes("riskli") || alignment.includes("aleyhe") || alignment.includes("dusuk");
  const raw = item.petition_paragraph || item.petition_usage_paragraph || item.legal_principle || item.short_summary || item.clean_text_preview || "";
  return cleanDecisionText(raw, risk ? RISK_PRECEDENT_PARAGRAPH : DEFAULT_PRECEDENT_PARAGRAPH);
}

function cleanDecisionText(value, fallback = CLEAN_PRECEDENT_EXPLANATION) {
  let text = cleanOutputText(value, fallback);
  text = text
    .replace(/İçtihat Metni/gi, "")
    .replace(/MAHKEMESİ\s*:\s*[^.]{0,160}/gi, "")
    .replace(/Kararda öne çıkan bağlantılar\s*:[^.]+\.?/gi, "")
    .replace(/Öne çıkan bağlantılar\s*:[^.]+\.?/gi, "")
    .replace(/aracın,\s*araç,\s*ayıp[^.]{0,120}/gi, "")
    .replace(/ayıp,\s*ayıplı,\s*bedel,\s*bilirkişi[^.]{0,120}/gi, "")
    .replace(/\s+/g, " ")
    .trim();
  const plain = plainText(text);
  if (
    !text ||
    plain.includes("kararda one cikan baglantilar") ||
    plain.includes("aracin arac ayip") ||
    plain.includes("ayip ayipli bedel bilirkisi") ||
    plain.includes("aracin ve aractaki ayibin")
  ) {
    return fallback;
  }
  return text;
}

function legalBrainFallbackCandidates() {
  return (lastBrainResults || [])
    .filter((item) => item.is_directly_relevant !== false && cleanOutputText(item.usable_argument) !== UNRELATED_ARGUMENT)
    .slice(0, 5)
    .map((item, index) => ({
      source_id: item.source_id || `legal_brain_${index + 1}`,
      title: item.title || item.section_title || item.citation_label || `Legal Brain kaynak ${index + 1}`,
      citation_label: item.citation_label || item.title || "",
      usable_argument: item.usable_argument || item.doctrine_principle || item.chunk_preview || "",
      relevance_reason: item.relevance_reason || item.reason || "",
      detail_url: item.detail_url || item.url || "",
      source_type: "legal_brain",
    }));
}

function decisionSourceLabel(item) {
  const sourceType = item.source_type || "unknown";
  if (sourceType === "yargitay_live") return "Canlı Yargıtay sonucu";
  if (sourceType === "legal_brain") return "Legal Brain yerel kaynak adayı — canlı Yargıtay doğrulaması yapılmadı";
  if (sourceType === "local_seed") return "Yerel emsal adayı — canlı Yargıtay doğrulaması yapılmadı";
  if (sourceType === "manual_uploaded") return "Elle yüklenen karar adayı";
  return "Kaynağı sınırlı emsal adayı";
}

function decisionUseClass(item) {
  const existing = plainText(item.use_class || "");
  if (existing) return item.use_class;
  const text = plainText(`${item.short_summary || ""} ${item.legal_principle || ""} ${item.petition_paragraph || ""} ${item.why_relevant || ""}`);
  const proceduralSignals = ["inceleme gorevi", "gonderilmesine", "gorevli daire", "temyiz sarti", "kesinlik", "on inceleme", "usul eksikligi", "hukuk dairesine gonderilmesine"];
  const substantiveSignals = ["gizli ayip", "servise basvuru", "ihtarname", "bilirkisi", "motor arizasi", "sanziman", "ekspertiz", "tramer", "pert", "agir hasar", "bedel indirimi", "sozlesmeden donme"];
  const proceduralHits = proceduralSignals.filter((term) => text.includes(term)).length;
  const substantiveHits = substantiveSignals.filter((term) => text.includes(term)).length;
  const summaryWords = plainText(item.short_summary || "").split(" ").filter(Boolean).length;
  if (proceduralHits && !substantiveHits) return "procedural_or_jurisdiction_only";
  if (summaryWords > 0 && summaryWords < 12) return substantiveHits ? "supporting_with_caution" : "insufficient_summary";
  if (item.source_type !== "yargitay_live" || item.official_verification_status !== "verified_live") return "exclude_from_petition";
  if (substantiveHits >= 3) return "direct_support";
  if (substantiveHits >= 1) return "supporting_with_caution";
  return "supporting_with_caution";
}

function decisionUseClassLabel(item) {
  const value = decisionUseClass(item);
  if (value === "direct_support") return "Doğrudan kullanılabilir";
  if (value === "supporting_with_caution") return "Dikkatli kullanılmalı";
  if (value === "procedural_or_jurisdiction_only") return "Sadece görev/usul yönünden";
  if (value === "distinguishable") return "Ayırt edilebilir";
  if (value === "insufficient_summary") return "Özet yetersiz — tam metin kontrol edilmeli";
  return "Dilekçeye alınmaz";
}

function renderDecisionCard(item, groupTitle) {
  const title = item.title || `${item.court || "Karar"} ${item.esas_no || ""}`;
  const detailLink = item.detail_url ? `<a href="${escapeHtml(item.detail_url)}" target="_blank" rel="noreferrer">Detay</a>` : "";
  const paragraph = cleanDecisionParagraph(item);
  const sourceLabel = decisionSourceLabel(item);
  const verification = item.official_verification_status || "not_verified";
  const showScores = (item.source_type || "unknown") === "yargitay_live";
  const scores = showScores ? decisionScoreBreakdown(item) : null;
  return `
    <div class="result-item">
      <h3>${escapeHtml(title)}</h3>
      <div class="meta-row">
        <span class="chip blue">${escapeHtml(groupTitle)}</span>
        <span class="chip">${escapeHtml(sourceLabel)}</span>
        <span class="chip">${escapeHtml(decisionUseClassLabel(item))}</span>
        <span class="chip">${escapeHtml(verification === "verified_live" ? "Resmî doğrulama: canlı" : "Resmî doğrulama yapılmadı")}</span>
        ${detailLink ? `<span class="chip">${detailLink}</span>` : ""}
      </div>
      <ol class="compact-list">
        <li><strong>Özet:</strong> ${escapeHtml(cleanOutputText(item.short_summary || paragraph, DEFAULT_PRECEDENT_PARAGRAPH))}</li>
        <li><strong>Kaynak durumu:</strong> ${escapeHtml(sourceLabel)}</li>
        <li><strong>Resmî doğrulama:</strong> ${escapeHtml(verification)}</li>
        <li><strong>Kullanım sınıfı:</strong> ${escapeHtml(decisionUseClassLabel(item))}</li>
        <li><strong>Somut olaya bağlantı:</strong> ${escapeHtml(item.why_relevant || item.petition_use_summary || paragraph)}</li>
      </ol>
      ${showScores && scores ? `<div class="score-grid">
        <span>Benzerlik: ${scores.similarity}</span>
        <span>Hukuki uygunluk: ${scores.legalFit}</span>
        <span>Güncellik: ${scores.recency}</span>
        <span>Risk: ${scores.riskLevel}</span>
        <span>Genel güç: ${scores.strength}</span>
      </div>` : ""}
    </div>
  `;
}

function decisionScoreBreakdown(item) {
  const similarity = Math.max(0, Math.min(100, Number(item.similarity_score ?? 55)));
  const plain = plainText(`${item.short_summary || ""} ${item.legal_principle || ""} ${item.petition_paragraph || ""} ${item.lehe_aleyhe || ""}`);
  const vehicleFit = ["arac", "otomobil", "ikinci el", "motor", "servis", "ekspertiz", "tramer"].filter((term) => plain.includes(term)).length;
  const hiddenDefectFit = ["gizli ayip", "bedel indirimi", "sozlesmeden donme", "ayip ihbari"].filter((term) => plain.includes(term)).length;
  const realEstateOnly = ["tasinmaz", "konut", "daire", "bagimsiz bolum"].some((term) => plain.includes(term)) && !vehicleFit;
  const legalFit = realEstateOnly
    ? Math.min(58, similarity)
    : vehicleFit
      ? Math.min(96, 58 + vehicleFit * 5 + hiddenDefectFit * 7)
      : Math.max(45, similarity - 12);
  const currentYear = new Date().getFullYear();
  const yearMatch = String(item.date || "").match(/(20\d{2}|19\d{2})/);
  const year = yearMatch ? Number(yearMatch[1]) : currentYear - 8;
  const recency = Math.max(35, Math.min(95, 95 - Math.max(0, currentYear - year) * 4));
  const risk = plain.includes("riskli") || plain.includes("aleyhe") || plain.includes("redd") ? 35 : realEstateOnly ? 62 : 86;
  const riskLevel = risk < 50 ? "Yüksek" : risk < 75 ? "Orta" : "Düşük";
  const strength = Math.round(similarity * 0.3 + legalFit * 0.35 + recency * 0.15 + risk * 0.2);
  return { similarity, legalFit, recency, risk, riskLevel, strength };
}

function renderDecisions(data) {
  lastYargitaySearch = data;
  const liveResults = data.live_yargitay_results || [];
  const fallbackResults = data.fallback_precedents || [];
  const decisions = data.final_precedents || data.top_decisions || [];
  const summary = data.source_summary || {};
  lastDecisions = decisions;
  els.decisionCount.textContent = String(decisions.length);
  const infoMessage = summary.live_yargitay_count > 0
    ? "Canlı Yargıtay aramasından gelen kararlar listeleniyor."
    : fallbackResults.length
      ? "Canlı Yargıtay araması sonuç döndürmedi. Aşağıdaki kararlar Legal Brain/yerel kaynak adaylarıdır; resmî doğrulama yapılmalıdır."
      : (data.errors || []).length
        ? precedentSearchMessage(data.errors || [])
        : "Bu denemede canlı Yargıtay sonucu bulunamadı.";
  if (!liveResults.length && !fallbackResults.length) {
    els.decisionOutput.className = "result-list";
    els.decisionOutput.innerHTML = `<div class="result-item"><h3>Emsal sonucu</h3><p>${escapeHtml(infoMessage)}</p></div>`;
    return;
  }
  const liveGroup = liveResults.length
    ? liveResults.map((item) => renderDecisionCard(item, "Canlı Yargıtay Sonuçları")).join("")
    : `<div class="result-item"><h3>Canlı Yargıtay Sonuçları</h3><p>Canlı Yargıtay araması bu denemede sonuç döndürmedi.</p></div>`;
  const fallbackGroup = fallbackResults.length
    ? fallbackResults.map((item) => renderDecisionCard(item, "Legal Brain / Yerel Kaynak Adaylar?")).join("")
    : "";
  els.decisionOutput.className = "result-list";
  els.decisionOutput.innerHTML = `
    <div class="result-item"><h3>Emsal Durumu</h3><p>${escapeHtml(infoMessage)}</p></div>
    ${liveGroup}
    ${fallbackGroup}
  `;
}


function renderStrategy(data) {
  lastStrategy = data;
  const basis = (data.legal_basis || []).slice(0, 4).join(", ");
  els.strategyOutput.className = "strategy-output active";
  els.strategyOutput.innerHTML = `
    <strong>${escapeHtml(data.petition_type || "Dilekçe")}</strong>
    ${basis ? `<br><span>${escapeHtml(basis)}</span>` : ""}
  `;
}

function normalizeQuestionFlow(questions) {
  const incoming = (questions?.length ? questions : fallbackQuestions).map((item) =>
    typeof item === "string" ? { question: item } : { question: item.question || String(item), options: item.suggested_answers || item.options || [] },
  );
  const base = currentProfileKey() === "defectiveVehicle" || vehicleContextActive() ? vehicleQuestionBank : incoming;
  return [...base, ...incoming]
    .filter((item) => item.question)
    .reduce((acc, item) => {
      const key = plainText(item.question);
      if (!acc.some((existing) => plainText(existing.question) === key)) {
        acc.push({
          question: item.question,
          options: sanitizeAnswerOptions(item.options?.length ? item.options : questionOptions(item.question)).slice(0, 5),
          requiredTerms: item.requiredTerms || [],
        });
      }
      return acc;
    }, [])
    .slice(0, 10);
}

function currentQuestionItem() {
  return questionFlow.questions[questionFlow.currentIndex] || null;
}

function saveQuestionField(field) {
  const question = field?.dataset.question;
  if (!question) return;
  const value = field.value.trim();
  if (value) {
    questionFlow.answers[question] = value;
    questionFlow.skipped.delete(question);
  } else {
    delete questionFlow.answers[question];
  }
  refreshQuestionAnswerCount();
}

function answerCurrentQuestion() {
  const item = currentQuestionItem();
  if (!item) return;
  const field = Array.from(els.questionFields.querySelectorAll("[data-question]"))
    .find((candidate) => candidate.dataset.question === item.question)
    || els.questionFields.querySelector("[data-question]");
  saveQuestionField(field);
}

function questionAnswerCount() {
  return Object.values(questionFlow.answers).filter((value) => String(value).trim()).length;
}

function refreshQuestionAnswerCount() {
  els.questionFields.querySelectorAll("[data-answer-count]").forEach((element) => {
    element.textContent = `${questionAnswerCount()} cevap`;
  });
}

function renderQuestionFields(questions) {
  const previousAnswers = { ...questionFlow.answers, ...buildAnswers() };
  questionFlow = {
    questions: normalizeQuestionFlow(questions),
    currentIndex: 0,
    answers: previousAnswers,
    skipped: new Set([...questionFlow.skipped].filter((question) => !previousAnswers[question])),
    showAll: false,
  };
  renderQuestionCard();
}

function renderQuestionCard() {
  if (!questionFlow.questions.length) {
    els.questionFields.innerHTML = '<div class="question-empty">Sorular henüz hazırlanmadı.</div>';
    return;
  }
  if (questionFlow.showAll) {
    els.questionFields.innerHTML = `
      <div class="question-flow-head">
        <strong>Tüm sorular</strong>
        <span data-answer-count>${questionAnswerCount()} cevap</span>
        <button class="ghost-btn small-btn" type="button" data-action="toggle-question-mode">Kart moduna dön</button>
      </div>
      ${questionFlow.questions
        .map((item, index) => {
          const value = questionFlow.answers[item.question] || "";
          const optionButtons = (item.options || questionOptions(item.question))
            .slice(0, 5)
            .map((option) => `<button class="answer-chip" type="button" data-option="${escapeHtml(option)}">${escapeHtml(option)}</button>`)
            .join("");
          return `
            <label class="question-card compact-question-card">
              <span>${index + 1}. ${escapeHtml(item.question)}</span>
              <textarea data-question="${escapeHtml(item.question)}" rows="2">${escapeHtml(value)}</textarea>
              <div class="answer-chips">${optionButtons}</div>
            </label>
          `;
        })
        .join("")}
      <button class="primary-btn small-btn" type="button" data-action="prepare-draft-from-questions">Dilekçeyi Hazırla</button>
    `;
    return;
  }
  const item = currentQuestionItem();
  const answeredCount = questionAnswerCount();
  const progress = `${questionFlow.currentIndex + 1} / ${questionFlow.questions.length}`;
  const value = questionFlow.answers[item.question] || "";
  const optionButtons = (item.options || questionOptions(item.question))
    .slice(0, 5)
    .map((option) => `<button class="answer-chip" type="button" data-option="${escapeHtml(option)}">${escapeHtml(option)}</button>`)
    .join("");
  const isLast = questionFlow.currentIndex >= questionFlow.questions.length - 1;
  els.questionFields.innerHTML = `
    <div class="question-flow-head">
      <strong>Soru ${progress}</strong>
      <span data-answer-count>${answeredCount} cevap</span>
    </div>
    <label class="question-card active-question-card">
      <span>${escapeHtml(item.question)}</span>
      <textarea data-question="${escapeHtml(item.question)}" rows="4" placeholder="Elle yaz">${escapeHtml(value)}</textarea>
      <div class="answer-chips" aria-label="Hazır cevap seçenekleri">${optionButtons}</div>
    </label>
    <div class="question-nav">
      <button class="ghost-btn small-btn" type="button" data-action="prev-question" ${questionFlow.currentIndex === 0 ? "disabled" : ""}>Geri</button>
      <button class="ghost-btn small-btn" type="button" data-action="skip-question">Atla</button>
      <button class="primary-btn small-btn" type="button" data-action="${isLast ? "prepare-draft-from-questions" : "next-question"}">
        ${isLast ? "Dilekçeyi Hazırla" : "Sonraki"}
      </button>
    </div>
    <button class="ghost-btn small-btn full-width-btn" type="button" data-action="toggle-question-mode">Tüm soruları göster</button>
  `;
}

function resetQuestions() {
  lastStrategy = null;
  lastStrategyCase = "";
  lastStrategyRequest = "";
  questionFlow = { questions: [], currentIndex: 0, answers: {}, skipped: new Set(), showAll: false };
  els.strategyOutput.className = "strategy-output";
  els.strategyOutput.innerHTML = "";
  els.questionFields.innerHTML = '<div class="question-empty">Sorular henüz hazırlanmadı.</div>';
}

function questionsAreCurrent() {
  return (
    lastStrategy &&
    lastStrategyCase === getCaseText() &&
    lastStrategyRequest === getRequestType() &&
    els.questionFields.querySelectorAll("[data-question]").length > 0
  );
}

function buildAnswers() {
  const answers = { ...questionFlow.answers };
  els.questionFields.querySelectorAll("[data-question]").forEach((field) => {
    const question = field.dataset.question;
    const answer = field.value.trim();
    if (question && answer) {
      answers[question] = answer;
      questionFlow.answers[question] = answer;
      questionFlow.skipped.delete(question);
    } else if (question) {
      delete answers[question];
      delete questionFlow.answers[question];
    }
  });
  refreshQuestionAnswerCount();
  return answers;
}

function handleQuestionOptionClick(event) {
  const actionButton = event.target.closest("[data-action]");
  if (actionButton) {
    const action = actionButton.dataset.action;
    if (action === "prev-question") {
      answerCurrentQuestion();
      questionFlow.currentIndex = Math.max(0, questionFlow.currentIndex - 1);
      renderQuestionCard();
      renderRisks();
      return;
    }
    if (action === "next-question") {
      answerCurrentQuestion();
      questionFlow.currentIndex = Math.min(questionFlow.questions.length - 1, questionFlow.currentIndex + 1);
      renderQuestionCard();
      renderRisks();
      return;
    }
    if (action === "skip-question") {
      const item = currentQuestionItem();
      if (item) {
        delete questionFlow.answers[item.question];
        questionFlow.skipped.add(item.question);
      }
      questionFlow.currentIndex = Math.min(questionFlow.questions.length - 1, questionFlow.currentIndex + 1);
      renderQuestionCard();
      renderRisks();
      return;
    }
    if (action === "toggle-question-mode") {
      answerCurrentQuestion();
      questionFlow.showAll = !questionFlow.showAll;
      renderQuestionCard();
      return;
    }
    if (action === "prepare-draft-from-questions") {
      answerCurrentQuestion();
      runDraft({ force: true }).catch((error) => setStatus(error.message, true));
      return;
    }
  }
  const button = event.target.closest(".answer-chip");
  if (!button) return;

  const card = button.closest(".question-card");
  const field = card?.querySelector("[data-question]");
  const value = button.dataset.option;
  if (!field || !value) return;

  appendAnswerOption(field, value);
  saveQuestionField(field);
  button.classList.add("selected");
  renderRisks();
  updateFinalPetitionReadiness();
  setStatus("Seçenek cevaba eklendi.");
}

function renderDraft(data) {
  els.draftOutput.textContent = cleanOutputText(data.petition_text || data.draft_text || "");
}

function documentContextText() {
  const documents = lastDocumentAnalysis?.documents || [];
  return documents
    .flatMap((documentItem) => [
      documentItem.document_type,
      documentItem.file_name,
      ...(documentItem.extracted_facts || [])
        .filter((fact) => fact.verification_status === "fact_confirmed")
        .flatMap((fact) => [DOCUMENT_FACT_LABELS[fact.fact_key] || fact.fact_key, fact.fact_value]),
    ])
    .join(" ");
}

function missingItemResolvedByDocuments(item) {
  const keys = new Set(documentFactPayload().map((fact) => fact.fact_key));
  const value = plainText(item);
  if (value.includes("satis bedel")) return keys.has("sale_price");
  if (value.includes("satis tarih")) return keys.has("sale_date");
  if (value.includes("marka") && value.includes("model") && value.includes("plaka") && value.includes("sasi")) {
    return ["vehicle_make_model", "vehicle_plate", "vehicle_vin"].every((key) => keys.has(key));
  }
  if (value.includes("marka") || value.includes("model")) return keys.has("vehicle_make_model");
  if (value.includes("plaka")) return keys.has("vehicle_plate");
  if (value.includes("sasi") || value.includes("sase")) return keys.has("vehicle_vin");
  if (value.includes("noter")) return keys.has("notary_info");
  if (value.includes("taraf")) return keys.has("parties");
  if (value.includes("dosya numara")) return keys.has("case_number");
  return false;
}

function issueConcept(item) {
  const value = plainText(item);
  if (value.includes("satis bedel")) return "sale_price";
  if ((value.includes("marka") || value.includes("model")) && (value.includes("plaka") || value.includes("sasi"))) return "vehicle_identity";
  if (value.includes("satis tarih")) return "sale_date";
  if (value.includes("ayip ihbar") || value.includes("bildirim tarih")) return "notice";
  if (value.includes("servis") || value.includes("ekspertiz")) return "technical_report";
  return value;
}

function dedupeIssues(items) {
  const seen = new Set();
  return (items || []).map((item) => cleanOutputText(item)).filter((item) => {
    if (!item) return false;
    const concept = issueConcept(item);
    if (seen.has(concept)) return false;
    seen.add(concept);
    return true;
  });
}

function riskLevelWeight(level) {
  const normalized = plainText(level);
  if (normalized.includes("high") || normalized.includes("yuksek")) return 3;
  if (normalized.includes("orta-yuksek")) return 2.5;
  if (normalized.includes("medium") || normalized.includes("orta")) return 2;
  return 1;
}

function riskLevelLabel(level) {
  const normalized = plainText(level);
  if (normalized.includes("high") || normalized.includes("yuksek")) return "Yüksek";
  if (normalized.includes("orta-yuksek")) return "Orta-Yüksek";
  if (normalized.includes("medium") || normalized.includes("orta")) return "Orta";
  return "Düşük";
}

function deriveOverallRiskLevel(dynamicLevel, reasonerRiskPlan = []) {
  const weights = [riskLevelWeight(dynamicLevel), ...reasonerRiskPlan.map((item) => riskLevelWeight(item.level || ""))];
  const highest = Math.max(...weights, 1);
  if (highest >= 3) return "Yüksek";
  if (highest >= 2.5) return "Orta-Yüksek";
  if (highest >= 2) return "Orta";
  return "Düşük";
}

function userFriendlyGroundingItems() {
  const labelMap = {
    parties: "Taraflar doğrulandı.",
    sale_date: "Satış tarihi doğrulandı.",
    sale_price: "Satış bedeli doğrulandı.",
    vehicle_make_model: "Araç marka/model doğrulandı.",
    vehicle_plate: "Plaka bilgisi doğrulandı.",
    vehicle_vin: "Şasi bilgisi doğrulandı.",
    claim_result: "Talep sonucu doğrulandı.",
  };
  return dedupeIssues(
    documentFactPayload()
      .map((fact) => labelMap[fact.fact_key] || "")
      .filter(Boolean),
  );
}

function precedentSearchMessage(errors = []) {
  const joined = plainText((errors || []).join(" "));
  if (joined.includes("chromium") || joined.includes("playwright") || joined.includes("captcha") || joined.includes("erişim") || joined.includes("runtime exception") || joined.includes("traceback")) {
    return "Emsal araması yapılamadı, yerel hukuki analiz devam etti.";
  }
  if (joined.includes("legal brain") || joined.includes("kaynak")) {
    return "Kaynak araması yapılamadı; emsal denetimi yerel verilerle sürdürüldü.";
  }
  return "Emsal araması şu anda tamamlanamadı; yerel hukuki analiz devam etti.";
}

function dynamicRiskState() {
  const rawCombined = [getCaseText(), getRequestType(), Object.values(buildAnswers()).join(" "), documentContextText()].join(" ");
  const combined = plainText(rawCombined);
  const profile = currentProfileKey();
  const caseState = currentCaseState();
  const completed = [];
  const partial = [];
  const missing = [];

  if (profile === "defectiveVehicle") {
    const hasDate = /\b\d{1,2}[./-]\d{1,2}[./-]\d{2,4}\b/.test(rawCombined) || /\b20\d{2}\b/.test(rawCombined);
    const hasAmount = /(?:₺|\btl\b|\blira\b|\b\d{4,}\b)/i.test(rawCombined);
    const hasSeller = ["galeri", "sirket", "gercek kisi", "tacir"].some((term) => combined.includes(term));
    const hasPartyNames = ["müvekkil", "muvekkil", "davacı", "davaci", "davalı", "davali", "satıcı", "satici", "alıcı", "alici"].some((term) => rawCombined.toLocaleLowerCase("tr-TR").includes(term));
    const hasSaleDoc = ["noter satis", "dekont", "banka dekontu", "elden odeme"].some((term) => combined.includes(term));
    const hasVehicleMarker = ["plaka", "sasi", "marka", "model"].some((term) => combined.includes(term));
    const hasReport = ["servis raporu", "ekspertiz raporu", "rapor"].some((term) => combined.includes(term));
    const hasReportDetail = hasReport && (hasDate || /rapor\s*(no|numara|numarası)/i.test(rawCombined));
    const hasTramer = combined.includes("tramer");
    const hasNotice = ["whatsapp", "sms", "noter ihtar", "bildirim", "ihbar"].some((term) => combined.includes(term));
    const hasDemand = ["bedel iadesi", "sozlesmeden donme", "bedel indirimi", "onarim gideri", "masraf"].some((term) => combined.includes(term));

    if (hasSeller) completed.push("Satıcı sıfatı");
    else missing.push("Satıcı galeri/şirket/tacir/gerçek kişi olarak netleştirilmeli");

    if (hasSaleDoc) completed.push("Satış belgesi / ödeme dayanağı");
    else missing.push("Satış belgesi ve ödeme dayanağı eklenmeli");

    if (hasAmount) completed.push("Satış bedeli miktarı");
    else if (combined.includes("bedel")) partial.push("Satış bedeli var, miktar girilmeli");
    else missing.push("Satış bedelinin miktarı girilmeli");

    if (hasDate) completed.push("Tarih bilgisi");
    else missing.push("Satış tarihi, ayıbın öğrenilme tarihi ve bildirim tarihi somutlaştırılmalı");

    if (hasVehicleMarker && (combined.includes("plaka") || combined.includes("sasi")) && (combined.includes("marka") || combined.includes("model"))) {
      completed.push("Araç marka/model/plaka/şasi bilgisi");
    } else if (hasVehicleMarker) {
      partial.push("Araç bilgisi kısmen tamamlandı; marka-model, plaka ve şasi bilgisi somutlaştırılmalı");
    } else {
      missing.push("Araç marka-model, plaka ve şasi bilgisi somutlaştırılmalı");
    }

    if (hasReportDetail) completed.push("Servis/ekspertiz rapor bilgisi");
    else if (hasReport) partial.push("Ayıp tespit belgesi kısmen tamamlandı; servis/ekspertiz rapor tarihi ve numarası yazılmalı");
    else missing.push("Servis/ekspertiz raporu veya teknik tespit belgesi eklenmeli");

    if (hasTramer && hasDate) completed.push("TRAMER/hasar kaydı içeriği");
    else if (hasTramer) partial.push("TRAMER kaydı kısmen tamamlandı; tarih ve içerik dosyaya eklenmeli");
    else missing.push("TRAMER kaydı varsa içeriği dosyaya eklenmeli");

    if (hasNotice && hasDate) completed.push("Ayıp ihbarı tarihi ve yöntemi");
    else if (hasNotice) partial.push("Ayıp ihbarı kısmen tamamlandı; bildirim tarihi ve tebliğ/mesaj kaydı eklenmeli");
    else missing.push("Ayıp ihbarının tarihi ve yöntemi netleştirilmeli");

    if (hasDemand) completed.push("Talep stratejisi");
    else missing.push("Asli ve terditli talep stratejisi netleştirilmeli");
  } else {
    const checks = [
      ["Taraf sıfatları", ["davaci", "davali", "muvekkil"]],
      ["Talep sonucu", ["talep", "dava", "kabul"]],
      ["Deliller", ["belge", "tanik", "rapor", "kayit", "dekont"]],
    ];
    checks.forEach(([label, terms]) => {
      if (terms.some((term) => combined.includes(term))) completed.push(label);
      else missing.push(label);
    });
  }

  const skipped = [...questionFlow.skipped].map((question) => `Atlandı: ${question}`);
  const answeredCount = Object.values(buildAnswers()).filter(Boolean).length;
  const missingCount = missing.length + skipped.length;
  const riskScore = missingCount * 2 + partial.length;
  const riskLevel = riskScore >= 12 ? "Yüksek" : riskScore >= 7 ? "Orta-Yüksek" : riskScore >= 4 ? "Orta" : "Düşük";
  const riskNotes = [];
  if (profile === "defectiveVehicle" && !completed.includes("Ayıp ihbarı tarihi ve yöntemi")) {
    riskNotes.push("Ayıp ihbarı tarihi ve yöntemi netleşmezse TBK m. 223 yönünden risk doğabilir.");
  }
  if (profile === "defectiveVehicle" && !completed.includes("Servis/ekspertiz rapor bilgisi")) {
    riskNotes.push("Servis/ekspertiz/TRAMER belgesi yoksa ayıbın satış anında mevcut olduğunu ispat güçleşir.");
  }
  return { completed, partial, missing: [...missing, ...skipped], riskLevel, riskNotes, answeredCount };
}

function enhancedDynamicRiskState() {
  const base = dynamicRiskState();
  const rawCombined = [getCaseText(), getRequestType(), Object.values(buildAnswers()).join(" "), documentContextText()].join(" ");
  const combined = plainText(rawCombined);
  const profile = currentProfileKey();
  const caseState = currentCaseState();
  const completed = [];
  const partial = [];
  const missing = [];

  if (profile === "defectiveVehicle") {
    const hasDate = /\b\d{1,2}[./-]\d{1,2}[./-]\d{2,4}\b/.test(rawCombined) || /\b20\d{2}\b/.test(rawCombined);
    const hasAmount = /(?:â‚º|\btl\b|\blira\b|\b\d{4,}\b)/i.test(rawCombined);
    const hasSeller = ["galeri", "sirket", "gercek kisi", "tacir"].some((term) => combined.includes(term));
    const hasPartyNames = ["müvekkil", "muvekkil", "davacı", "davaci", "davalı", "davali", "satıcı", "satici", "alıcı", "alici"].some((term) => rawCombined.toLocaleLowerCase("tr-TR").includes(term));
    const hasSaleDoc = ["noter satis", "dekont", "banka dekontu", "elden odeme"].some((term) => combined.includes(term));
    const hasVehicleMarker = ["plaka", "sasi", "marka", "model"].some((term) => combined.includes(term));
    const hasReport = ["servis raporu", "ekspertiz raporu", "rapor"].some((term) => combined.includes(term));
    const hasReportDetail = hasReport && (hasDate || /rapor\s*(no|numara|numarası)/i.test(rawCombined));
    const hasTramer = combined.includes("tramer");
    const hasNotice = ["whatsapp", "sms", "noter ihtar", "bildirim", "ihbar"].some((term) => combined.includes(term));
    const hasDemand = ["bedel iadesi", "sozlesmeden donme", "bedel indirimi", "onarim gideri", "masraf"].some((term) => combined.includes(term));

    if (hasPartyNames) completed.push("Taraf isimleri");
    else missing.push("Taraf isimleri açıkça yazılmalı");

    if (hasSeller) completed.push("Satıcı sıfatı / görevli mahkeme");
    else missing.push("Satıcının tacir/galeri/şirket/gerçek kişi sıfatı netleştirilmeli");

    if (hasSaleDoc) completed.push("Satış belgesi / ödeme dayanağı");
    else missing.push("Satış belgesi ve ödeme dayanağı eklenmeli");

    if (hasAmount) completed.push("Satış bedeli");
    else if (combined.includes("bedel")) partial.push("Satış bedeli var, miktar girilmeli");
    else missing.push("Satış bedelinin miktarı girilmeli");

    if (hasDate) completed.push("Satış tarihi");
    else missing.push("Satış tarihi, ayıbın öğrenilme tarihi ve bildirim tarihi somutlaştırılmalı");

    if (hasVehicleMarker && (combined.includes("plaka") || combined.includes("sasi")) && (combined.includes("marka") || combined.includes("model"))) {
      completed.push("Araç marka/model");
      completed.push("Plaka/şasi");
    } else if (hasVehicleMarker) {
      partial.push("Araç bilgisi kısmen tamamlandı; marka-model, plaka ve şasi bilgisi somutlaştırılmalı");
    } else {
      missing.push("Araç marka-model, plaka ve şasi bilgisi somutlaştırılmalı");
    }

    if (hasReportDetail) completed.push("Servis/ekspertiz raporu");
    else if (hasReport) partial.push("Servis/ekspertiz raporu var; rapor tarihi ve numarası yazılmalı");
    else missing.push("Servis/ekspertiz rapor tarihi ve rapor numarası eklenmeli");

    if (hasTramer && hasDate) completed.push("TRAMER/hasar kaydı");
    else if (hasTramer) partial.push("TRAMER kaydı var; tarih ve içerik dosyaya eklenmeli");
    else missing.push("TRAMER/ağır hasar/gizli onarım kaydı araştırılmalı");

    if (hasNotice && hasDate) completed.push("Ayıp ihbarı");
    else if (hasNotice) partial.push("Ayıp ihbarı var; bildirim tarihi ve yöntemi netleştirilmeli");
    else missing.push("Ayıp ihbar tarihi ve yöntemi netleştirilmeli");

    if (hasDemand) completed.push("Talep sonucu");
    else missing.push("Asli ve terditli talep stratejisi netleştirilmeli");
  } else {
    const checks = [
      ["Taraf isimleri", ["davaci", "davali", "muvekkil"]],
      ["Talep sonucu", ["talep", "dava", "kabul"]],
      ["Deliller", ["belge", "tanik", "rapor", "kayit", "dekont"]],
    ];
    checks.forEach(([label, terms]) => {
      if (terms.some((term) => combined.includes(term))) completed.push(label);
      else missing.push(label);
    });
  }

  const riskLevel = deriveOverallRiskLevel(base.riskLevel, caseStatePlanItems(caseState, "risk_plan"));
  const riskNotes = [...base.riskNotes];
  return {
    ...base,
    completed,
    partial,
    missing: [...missing, ...[...questionFlow.skipped].map((question) => `Atlandı: ${question}`)],
    riskLevel,
    riskNotes,
  };
}

function renderRisks({ caseEnrichment = lastCaseEnrichment, draftAudit = null, sourceAudit = null, precedentAudit = null, draftWarnings = [], draftGrounding = [] } = {}) {
  const cards = [];
  const caseState = currentCaseState();
  const reasonerRiskPlan = caseStatePlanItems(caseState, "risk_plan");
  const dynamic = enhancedDynamicRiskState();
  const missing = dedupeIssues([
    ...dynamic.missing,
    ...(caseEnrichment?.missing_facts || []),
    ...(draftAudit?.missing_facts || []),
    ...documentMissingFields(),
  ].filter((item) => !missingItemResolvedByDocuments(item)));
  const riskFlags = [
    `Genel risk seviyesi: ${riskLevelLabel(dynamic.riskLevel)}`,
    ...reasonerRiskPlan.map((item) => `${riskLevelLabel(item.level || "")}: ${item.title || "Risk"} - ${item.reason || "Sebep belirtilmedi."}`),
    ...dynamic.riskNotes,
    ...(caseEnrichment?.risk_flags || []),
    ...(draftAudit?.critical_issues || []),
    ...(draftAudit?.major_issues || []),
  ];
  const rejectedSourceCount = (sourceAudit?.audited_sources || []).filter((item) => !item.use_in_petition).length;
  const sourceProblems = [
    ...(draftAudit?.source_problems || []),
    rejectedSourceCount ? "Konu dışı kaynaklar filtrelendi." : "",
  ].filter(Boolean);
  const safeDraftDecisionCount = mapSelectedDecisions().length;
  const riskyAuditItems = (precedentAudit?.audited_precedents || []).filter((item) => item.alignment === "riskli" || item.alignment === "aleyhe");
  const precedentProblems = [
    ...(draftAudit?.precedent_problems || []).filter((item) => {
      const plain = plainText(item);
      if (plain.includes("tekrar") && safeDraftDecisionCount) return false;
      if (plain.includes("riskli") && safeDraftDecisionCount) return false;
      return true;
    }),
    !safeDraftDecisionCount && lastDecisions.length ? "Emsaller bulundu; ancak güvenli biçimde dilekçeye alınabilecek doğrudan lehe emsal sınırlı." : "",
    riskyAuditItems.length && !safeDraftDecisionCount ? "Riskli/aleyhe kararlar talebi destekler gibi kullanılmadı." : "",
  ].filter(Boolean);
  const languageProblems = [...(draftAudit?.petition_language_problems || []), ...(draftWarnings || [])];
  const groundingNotes = userFriendlyGroundingItems();
  const documentGrounding = documentFactPayload().map((fact) => {
    const label = DOCUMENT_FACT_LABELS[fact.fact_key] || fact.fact_key;
    return `[fact_confirmed] ${label}: ${fact.fact_value} — Kaynak: ${fact.source_file_name}${fact.page_number ? `, s. ${fact.page_number}` : ""}`;
  });
  const documentProblems = [
    ...(lastDocumentAnalysis?.warnings || []),
    ...(lastDocumentAnalysis?.conflicts || []).map((conflict) => conflict.warning),
  ];

  const pushCard = (title, items, badgeClass = "info") => {
    const cleanItems = dedupeIssues(items);
    if (!cleanItems.length) return;
    cards.push({ title, items: cleanItems, badgeClass });
  };

  const graph = lastLegalIssueGraph;
  if (graph && Array.isArray(graph.issues)) {
    for (const issue of graph.issues) {
      const riskLabel = riskLevelLabel(issue.risk_level || "low");
      const items = [];
      if (issue.missing_facts?.length) {
        items.push(...issue.missing_facts.map((f) => `Eksik vakıa: ${f}`));
      }
      if (issue.missing_evidence?.length) {
        items.push(...issue.missing_evidence.map((e) => `Eksik delil: ${e}`));
      }
      if (issue.risk_reason) {
        items.push(`Risk sebebi: ${issue.risk_reason}`);
      }
      if (issue.client_questions?.length) {
        items.push(`Müvekkil sorusu: ${issue.client_questions[0]}`);
      }
      if (!items.length) continue;
      const riskClass = riskLabel.includes("Yüksek") ? "danger" : riskLabel.includes("Orta") ? "warning" : "info";
      cards.push({ title: issue.title, items, badgeClass: riskClass, riskBadge: riskLabel });
    }
  }
  if (graph?.global_risks?.length) {
    pushCard("Graph Genel Riskler", graph.global_risks, "danger");
  }

  pushCard("Eksik Bilgiler", missing, "warning");
  pushCard("Kısmen Tamamlananlar", dynamic.partial, "warning");
  pushCard("Tamamlananlar", dynamic.completed, "info");
  pushCard("Dava riskleri", riskFlags, "danger");
  pushCard("Emsal denetimi", precedentProblems, "warning");
  pushCard("Kaynak denetimi", sourceProblems, "warning");
  pushCard("Belge analizi", documentProblems, "warning");
  pushCard("Vakıa / kaynak grounding", [...documentGrounding, ...groundingNotes], "info");
  pushCard("Dilekçe Notları", languageProblems, "info");

  pushCard(
    "Reasoner risk plani",
    reasonerRiskPlan.map((item) => `[${String(item.level || "info").toUpperCase()}] ${item.title || "Risk"}: ${item.reason || "Sebep belirtilmedi."} Mitigasyon: ${item.mitigation || "Belirtilmedi."}`),
    "danger",
  );
  const visibleCards = cards.filter((card) => {
    const title = plainText(card.title);
    return !title.includes("grounding") && !title.includes("reasoner risk plani");
  });
  if (groundingNotes.length) {
    visibleCards.push({ title: "Belgeyle doğrulanan bilgiler", items: groundingNotes, badgeClass: "info" });
  }
  els.riskCount.textContent = String(visibleCards.reduce((total, card) => total + card.items.length, 0));
  if (!visibleCards.length) {
    els.riskOutput.className = "empty-state";
    els.riskOutput.textContent = "Belirgin eksik veya kritik risk bulunmadı.";
    return;
  }
  els.riskOutput.className = "risk-list";
  els.riskOutput.innerHTML = visibleCards
    .map(
      (card) => `
        <div class="risk-card">
           <h3>${escapeHtml(card.title)} <span class="risk-badge ${card.badgeClass}">${card.riskBadge || card.items.length}</span></h3>
          <ol class="compact-list">${card.items.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ol>
        </div>
      `,
    )
    .join("");
}

// ── P1.7 Hukuki Mesele Haritası ──

async function fetchLegalMap() {
  if (!activeCaseId) {
    els.legalMapSummary.className = "legalmap-summary empty-state";
    els.legalMapSummary.textContent = "Aktif dosya bulunamadı.";
    return;
  }
  try {
    const summary = await apiPost(`/api/cases/${activeCaseId}/legal-graph/summary`, { case_id: activeCaseId });
    lastLegalMapGraph = summary;
    renderLegalMapSummary(summary);
    await fetchLegalMapGraph();
  } catch (e) {
    els.legalMapSummary.className = "legalmap-summary empty-state";
    els.legalMapSummary.textContent = "Harita yüklenemedi: " + (e.message || "bağlantı hatası");
  }
}

async function fetchLegalMapGraph() {
  if (!activeCaseId) return;
  try {
    const graph = await apiPost(`/api/cases/${activeCaseId}/legal-graph`, { case_id: activeCaseId });
    lastLegalMapGraph = graph;
    renderLegalMapFull(graph);
  } catch (e) {
    els.legalMapIssues.style.display = "none";
    els.legalMapGraphData.style.display = "none";
  }
}

function renderLegalMapSummary(summary) {
  if (!summary || summary.total_nodes === 0) {
    els.legalMapSummary.className = "legalmap-summary empty-state";
    els.legalMapSummary.innerHTML = "<p>Henüz harita oluşturulmadı. Haritayı Oluştur butonuna tıklayın.</p>";
    els.legalMapIssues.style.display = "none";
    els.legalMapGraphData.style.display = "none";
    els.legalMapNodeEditor.style.display = "none";
    return;
  }
  els.legalMapSummary.className = "legalmap-summary";
  els.legalMapSummary.innerHTML = `
    <div class="legalmap-stats">
      <div class="stat-item"><span class="stat-value">${summary.legal_issue_count}</span><span class="stat-label">Hukuki Mesele</span></div>
      <div class="stat-item"><span class="stat-value">${summary.fact_count}</span><span class="stat-label">Vakıa</span></div>
      <div class="stat-item"><span class="stat-value">${summary.evidence_count}</span><span class="stat-label">Delil</span></div>
      <div class="stat-item"><span class="stat-value">${summary.official_source_count}</span><span class="stat-label">Resmî Kaynak</span></div>
      <div class="stat-item"><span class="stat-value">${summary.risk_count}</span><span class="stat-label">Risk</span></div>
      <div class="stat-item"><span class="stat-value">${summary.missing_information_count}</span><span class="stat-label">Eksik Bilgi</span></div>
    </div>
    <div class="legalmap-validation">
      Doğrulama: ${summary.validation_valid ? '<span class="chip green">Geçerli</span>' : '<span class="chip red">Uyarılar var</span>'}
      ${summary.validation_warning_count ? ` (${summary.validation_warning_count} uyarı)` : ''}
    </div>
  `;
  els.legalMapNodeEditor.style.display = "block";
}

function renderLegalMapFull(graph) {
  if (!graph || !graph.nodes || graph.nodes.length === 0) {
    els.legalMapIssues.style.display = "none";
    els.legalMapGraphData.style.display = "none";
    return;
  }

  const nodes = graph.nodes;
  const edges = graph.edges || [];
  const nodeMap = {};
  nodes.forEach((n) => { nodeMap[n.id] = n; });

  const issues = nodes.filter((n) => n.node_type === "legal_issue");
  if (issues.length) {
    els.legalMapIssues.style.display = "block";
    els.legalMapIssues.innerHTML = "<h3>Hukuki Meseleler</h3>" + issues.map((issue) => {
      const connected = edges.filter((e) => e.source_node_id === issue.id || e.target_node_id === issue.id);
      const relatedNodes = connected.map((e) => {
        const otherId = e.source_node_id === issue.id ? e.target_node_id : e.source_node_id;
        const other = nodeMap[otherId];
        if (!other) return null;
        const relLabel = { supports: "Destekliyor", requires: "Gerektiriyor", depends_on: "Bağlı", leads_to: "Yönlendiriyor" }[e.relation_type] || e.relation_type;
        return `<li>${relLabel}: <strong>${escapeHtml(other.title)}</strong> <span class="chip small">${other.node_type}</span> <span class="chip ${other.status === 'confirmed' ? 'green' : 'blue'} small">${other.status}</span></li>`;
      }).filter(Boolean).join("");
      return `
        <div class="legalmap-issue-card">
          <h4>${escapeHtml(issue.title)} <span class="chip ${issue.status === 'confirmed' ? 'green' : 'blue'}">${issue.status}</span></h4>
          ${issue.description ? `<p>${escapeHtml(issue.description)}</p>` : ""}
          ${relatedNodes ? `<ul class="compact-list">${relatedNodes}</ul>` : "<p>Bağlantı yok.</p>"}
        </div>
      `;
    }).join("");
  } else {
    els.legalMapIssues.style.display = "none";
  }

  rimNodes = nodes;
  rimEdges = edges;
}

let rimNodes = [];
let rimEdges = [];

function renderLegalMapMissing(validation) {
  if (!validation || (!validation.errors.length && !validation.warnings.length)) {
    els.legalMapMissingOutput.style.display = "block";
    els.legalMapMissingOutput.className = "legalmap-missing";
    els.legalMapMissingOutput.innerHTML = "<p>Tüm bağlantılar tutarlı, eksik veya kritik uyarı bulunamadı.</p>";
    return;
  }
  els.legalMapMissingOutput.style.display = "block";
  els.legalMapMissingOutput.className = "legalmap-missing";
  const errorHtml = validation.errors.map((e) => `<li class="danger">HATA: ${escapeHtml(e.detail)}</li>`).join("");
  const warningHtml = validation.warnings.map((w) => `<li class="warning">UYARI [${w.type}]: ${escapeHtml(w.detail)}</li>`).join("");
  els.legalMapMissingOutput.innerHTML = `
    ${errorHtml ? `<h4>Hatalar</h4><ul class="compact-list">${errorHtml}</ul>` : ""}
    ${warningHtml ? `<h4>Uyarılar</h4><ul class="compact-list">${warningHtml}</ul>` : ""}
    ${!errorHtml && !warningHtml ? "<p>Tüm bağlantılar tutarlı.</p>" : ""}
  `;
}

async function rebuildLegalMap() {
  if (!activeCaseId) return;
  setStatus("Harita oluşturuluyor...");
  try {
    const result = await apiPost(`/api/cases/${activeCaseId}/legal-graph/rebuild`, { case_id: activeCaseId });
    lastLegalMapGraph = result;
    await fetchLegalMap();
    setStatus("Harita güncellendi.");
  } catch (e) {
    setStatus("Harita oluşturulamadı: " + (e.message || "hata"));
  }
}

async function validateLegalMap() {
  if (!activeCaseId) return;
  setStatus("Doğrulanıyor...");
  try {
    const validation = await apiPost(`/api/cases/${activeCaseId}/legal-graph/validate`, { case_id: activeCaseId });
    lastLegalMapValidation = validation;
    renderLegalMapMissing(validation);
    setStatus(validation.valid ? "Harita geçerli." : "Haritada sorunlar bulundu.");
  } catch (e) {
    setStatus("Doğrulama başarısız: " + (e.message || "hata"));
  }
}

async function addLegalMapNode() {
  if (!activeCaseId) return;
  const nodeType = els.legalMapNodeType.value;
  const status = els.legalMapNodeStatus.value;
  const title = els.legalMapNodeTitle.value.trim();
  if (!title) { setStatus("Başlık gerekli."); return; }
  setStatus("Düğüm ekleniyor...");
  try {
    await apiPost(`/api/cases/${activeCaseId}/legal-graph/nodes`, {
      case_id: activeCaseId,
      node_type: nodeType,
      title: title,
      status: status,
      source_type: "user_input",
    });
    els.legalMapNodeTitle.value = "";
    await fetchLegalMap();
    setStatus("Düğüm eklendi.");
  } catch (e) {
    setStatus("Düğüm eklenemedi: " + (e.message || "hata"));
  }
}

function clearLegalMapState() {
  lastLegalMapGraph = null;
  lastLegalMapValidation = null;
  rimNodes = [];
  rimEdges = [];
  els.legalMapSummary.className = "legalmap-summary empty-state";
  els.legalMapSummary.textContent = "Henüz harita oluşturulmadı.";
  els.legalMapIssues.style.display = "none";
  els.legalMapIssues.innerHTML = "";
  els.legalMapGraphData.style.display = "none";
  els.legalMapMissingOutput.style.display = "none";
  els.legalMapNodeEditor.style.display = "none";
}

function renderReviewSummary({ analysis = null, enrichment = null, sourceCount = 0, precedentCount = 0, qualityScore = null } = {}) {
  const topic = enrichment?.detected_case_type || analysis?.legal_topic || "Hukuki inceleme";
  const keywords = enrichment?.search_keywords || analysis?.legal_keywords || [];
  els.analysisCount.textContent = String((keywords || []).length);
  els.analysisOutput.className = "result-list";
  els.analysisOutput.innerHTML = `
    <div class="result-item">
      <h3>${escapeHtml(topic)}</h3>
      <div class="meta-row">
        ${qualityScore !== null ? `<span class="chip blue">${escapeHtml(qualityScore)} kalite</span>` : ""}
        <span class="chip">${escapeHtml(sourceCount)} kaynak</span>
        <span class="chip">${escapeHtml(precedentCount)} emsal</span>
        <span class="chip">${enrichment?.ai_used ? "Gemini" : "Fallback"}</span>
      </div>
      <ol class="compact-list">
        <li>Olay analizi, kaynak taraması, emsal denetimi ve dilekçe kalite kontrolü tamamlandı.</li>
        <li>Eksik bilgi ve riskler ayrı sekmede tutuldu; dilekçe metnine ham analiz notu eklenmedi.</li>
        <li>Dilekçe sekmesindeki metin avukat kontrolüne hazır ilk taslak olarak düzenlendi.</li>
      </ol>
    </div>
    ${
      keywords.length
        ? `<div class="result-item"><h3>Anahtar kavramlar</h3><div class="meta-row">${keywords
            .slice(0, 12)
            .map((item) => `<span class="chip">${escapeHtml(item)}</span>`)
            .join("")}</div></div>`
        : ""
    }
  `;
}

function vehicleClientQuestions() {
  return [
    "Aracı hangi tarihte aldınız?",
    "Satış bedeli kaç TL?",
    "Satıcı galeri/şirket miydi, gerçek kişi miydi?",
    "Ödeme nasıl yapıldı ve dekont var mı?",
    "Araçta arıza ne zaman ortaya çıktı?",
    "Servis veya ekspertiz raporu var mı?",
    "TRAMER/hasar kaydı var mı?",
    "Satıcıya ne zaman ve nasıl bildirim yaptınız?",
    "Noter ihtarnamesi gönderildi mi?",
    "Onarım, ekspertiz ve servis masrafları kaç TL?",
  ];
}

function defenseSimulationItems() {
  if (currentProfileKey() !== "defectiveVehicle") {
    return [
      ["Somut vakıalar eksik", "Eksik tarih, belge ve deliller tamamlanmalıdır.", "Belge/tanık/resmi kayıt", "Orta"],
      ["İspat yükü davacıda", "Her vakıa delille eşleştirilmelidir.", "Delil listesi ve bilirkişi", "Orta"],
    ];
  }
  return [
    ["Araç görülerek alındı.", "Ayıp gizli niteliktedir; olağan muayene ile fark edilmesi beklenemez.", "Servis/ekspertiz raporu, bilirkişi", "Orta"],
    ["Arıza satıştan sonra oluştu.", "Arızanın satıştan önce mevcut olduğu teknik inceleme ile ispatlanmalıdır.", "Servis kayıtları, TRAMER, bilirkişi", "Yüksek"],
    ["Ayıp ihbarı süresinde yapılmadı.", "Bildirim tarihi WhatsApp, SMS, noter ihtarı veya tebliğ kayıtlarıyla somutlaştırılmalıdır.", "Yazışma, ihtarname, tebliğ şerhi", "Orta"],
    ["Satıcı ayıbı bilmiyordu.", "TBK ayıptan sorumluluk rejimi kapsamında bildirilmeyen gizli ayıp ayrıca değerlendirilmelidir.", "Satış ilanı, beyanlar, teknik kayıtlar", "Orta"],
  ];
}

function renderLegalIssueGraph() {
  const graph = lastLegalIssueGraph;
  const output = els.legalIssueGraphOutput;
  if (!output) return;
  if (!graph || !Array.isArray(graph.issues) || !graph.issues.length) {
    output.style.display = "none";
    return;
  }
  output.style.display = "block";
  output.className = "legal-issue-graph";
  const issueCards = graph.issues.map((issue) => {
    const riskLabel = riskLevelLabel(issue.risk_level || "low");
    const riskClass = plainText(riskLabel).includes("yuksek") ? "danger" : plainText(riskLabel).includes("orta") ? "warning" : "info";
    const missingFacts = (issue.missing_facts || []).filter(Boolean);
    const missingEvidence = (issue.missing_evidence || []).filter(Boolean);
    const clientQuestions = (issue.client_questions || []).filter(Boolean);
    const petitionArg = issue.petition_argument || "";
    return `
      <div class="result-item">
        <h3>Hukuki Mesele: ${escapeHtml(issue.title || "Belirtilmemiş")}</h3>
        <div class="meta-row">
          <span class="chip ${riskClass}">Risk: ${escapeHtml(riskLabel)}</span>
        </div>
        <ol class="compact-list">
          ${missingFacts.length ? `<li><strong>Eksik vakıa:</strong> ${escapeHtml(missingFacts.join("; "))}</li>` : ""}
          ${missingEvidence.length ? `<li><strong>Eksik delil:</strong> ${escapeHtml(missingEvidence.join("; "))}</li>` : ""}
          ${clientQuestions.length ? `<li><strong>Sorulacak soru:</strong> ${escapeHtml(clientQuestions[0])}</li>` : ""}
          ${petitionArg ? `<li><strong>Dilekçe argümanı:</strong> ${escapeHtml(petitionArg)}</li>` : ""}
        </ol>
      </div>
    `;
  }).join("");
  output.innerHTML = `
    <div class="section-head" style="margin-top:1.5rem">
      <h3>Hukuki Mesele Haritası</h3>
    </div>
    ${issueCards}
  `;
}

async function fetchLegalIssueGraph() {
  if (!activeCaseId) return null;
  try {
    const data = await apiFetch(caseQuery("/case/legal-issue-graph"));
    if (!data.ok) {
      lastLegalIssueGraph = null;
      renderLegalIssueGraph();
      renderRisks();
      return null;
    }
    const graph = await data.json();
    lastLegalIssueGraph = graph && typeof graph === "object" ? graph : null;
    renderLegalIssueGraph();
    renderRisks();
    return lastLegalIssueGraph;
  } catch {
    lastLegalIssueGraph = null;
    renderLegalIssueGraph();
    renderRisks();
    return null;
  }
}

function renderStrategyToolkit() {
  const caseState = currentCaseState();
  const questionPlan = caseStatePlanItems(caseState, "question_plan");
  const dynamic = enhancedDynamicRiskState();
  const answers = buildAnswers();
  const profile = currentProfileKey();
  const hasDecisions = lastDecisions.length > 0;
  const directSources = lastBrainResults.filter((item) => item.is_directly_relevant !== false);
  const strategyGroups = [
    ["Güçlü yönler", [
      profile === "defectiveVehicle" ? "Satıcı beyanı, kısa sürede ortaya çıkan arıza ve teknik tespit birlikte kurulursa gizli ayıp anlatımı güçlenir." : "Olay, talep ve delil bağlantısı netleştirildikçe dava iskeleti güçlenir.",
      dynamic.completed.length ? `Tamamlanan bilgi başlıkları: ${dynamic.completed.join(", ")}.` : "",
    ]],
    ["Kısmen tamamlanan bilgi", dynamic.partial.length ? dynamic.partial : ["Kısmen tamamlanan başlık yok."]],
    ["Somutlaştırılması gereken bilgi", dynamic.missing.length ? dynamic.missing.map((item) => `${item}.`) : ["Belirgin kritik eksik şimdilik görünmüyor."]],
    ["Kritik eksik / görev listesi", profile === "defectiveVehicle" ? [
      "Satış tarihi ve satış bedeli somutlaştırılmalı.",
      "Araç marka/model/plaka/şasi bilgisi eklenmeli.",
      "Servis raporunun tarih, numara ve içeriği belirtilmeli.",
      "Bildirim tarihi WhatsApp/SMS veya noter ihtarıyla ispatlanmalı.",
      "TRAMER kaydı varsa içeriği dosyaya eklenmeli.",
    ] : dynamic.missing.map((item) => `${item} tamamlanmalı.`)],
    ["İspat stratejisi", profile === "defectiveVehicle" ? [
      "Servis/ekspertiz/TRAMER kayıtları ve bilirkişi incelemesi ile ayıbın niteliği ve satış anındaki varlığı ispatlanmalı.",
      "Satıcı beyanları ilan, mesaj ve tanıkla desteklenmeli.",
    ] : ["Her vakıa, belge veya tanıkla eşleştirilmeli."]],
    ["Delil tamamlama planı", [
      "Eksik bilgi başlıkları tamamlanmalı.",
      directSources.length ? "Doğrudan ilgili Legal Brain kaynakları dilekçe dayanaklarıyla kontrol edilmeli." : "Doğrudan ilgili kaynak bulunmadıysa kanun maddesi ve emsal taraması ayrıca teyit edilmeli.",
    ]],
    ["Muhtemel davalı savunmaları ve cevaplar", defenseSimulationItems().map(([defense, answer]) => `${defense} Cevap: ${answer}`)],
    ["Asli / terditli talep stratejisi", [
      profile === "defectiveVehicle" ? "Asli talep sözleşmeden dönme ve bedel iadesi; terditli talep bedel indirimi ve masrafların tahsili olarak korunmalı." : "Asli ve terditli talepler dava türüne göre açık ayrılmalı.",
    ]],
    ["Görev, yetki, süre, dava şartı", [
      profile === "defectiveVehicle" ? "Satıcının tacir/galeri olup olmadığına göre Tüketici Mahkemesi / Asliye Hukuk değerlendirmesi yapılmalı." : "Görev, yetki ve dava şartı dosya özelinde kontrol edilmeli.",
      `Güncel risk seviyesi: ${dynamic.riskLevel}.`,
    ]],
    ["Emsal kullanımı", [
      hasDecisions ? "Lehe ve doğrudan bağlantılı kararlar numara, tarih ve kısa özetle kullanılmalı; riskli kararlar dilekçeye lehe gibi alınmamalı." : "Emsal bulunmadıysa karar numarası uydurulmadan emsal bölümü boş/temkinli bırakılmalı.",
    ]],
    ["Dava açmadan önce", dynamic.missing.length ? dynamic.missing.map((item) => `${item} tamamlanmalı.`).join(" ") : "Mevcut bilgilerle ilk taslak hazırlanabilir; son kontrol avukatta olmalı."],
  ];
  els.strategyCount.textContent = String(strategyGroups.length);
  els.strategyTabOutput.className = "result-list";
  els.strategyTabOutput.innerHTML = strategyGroups
    .map(([title, items]) => {
      const list = Array.isArray(items) ? items.filter(Boolean) : [items].filter(Boolean);
      return `<div class="result-item"><h3>${escapeHtml(title)}</h3><ol class="compact-list">${list.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ol></div>`;
    })
    .join("");

  const clientQuestions = profile === "defectiveVehicle" ? vehicleClientQuestions() : questionFlow.questions.map((item) => item.question).slice(0, 10);
  els.clientQuestionsOutput.className = "result-list";
  els.clientQuestionsOutput.innerHTML = `<div class="result-item"><h3>Müvekkile gönderilecek kısa liste</h3><ol class="compact-list">${clientQuestions
    .map((item) => `<li>${escapeHtml(item)}</li>`)
    .join("")}</ol></div>`;

  if (questionPlan.length) {
    els.clientQuestionsOutput.innerHTML = `<div class="result-item"><h3>Muvekkile gonderilecek kisa liste</h3><ol class="compact-list">${questionPlan
      .map((item) => `<li><strong>${escapeHtml(item.question || "Soru")}</strong><br><small>Neden: ${escapeHtml(item.reason || "Belirtilmedi")}</small></li>`)
      .join("")}</ol></div>`;
  }

  const defenses = defenseSimulationItems();
  els.defenseCount.textContent = String(defenses.length);
  els.defenseOutput.className = "result-list";
  els.defenseOutput.innerHTML = defenses
    .map(
      ([defense, answer, evidence, risk]) => `
        <div class="result-item">
          <h3>${escapeHtml(defense)}</h3>
          <div class="meta-row"><span class="chip blue">Risk: ${escapeHtml(risk)}</span><span class="chip">${escapeHtml(evidence)}</span></div>
          <p>${escapeHtml(answer)}</p>
        </div>
      `,
    )
    .join("");

  renderOfficialSourcesStatus();
}

function renderOfficialSourcesStatus() {
  const sources = [
    ["Resmî Gazete", "Whitelist", "Kanun ve yönetmelik değişiklikleri için resmi kaynak."],
    ["Mevzuat kaynakları", "Whitelist", "Mevzuat doğrulaması için izinli/resmî kaynak."],
    ["Yargıtay Karar Arama", "Whitelist", "Emsal karar taraması için resmî kaynak."],
    ["UYAP Emsal", "Whitelist", "UYAP emsal taraması için resmî/izinli kaynak."],
    ["Danıştay", "Whitelist", "İdari yargı içtihatları için resmî kaynak."],
    ["Anayasa Mahkemesi", "Whitelist", "AYM kararları için resmî kaynak."],
    ["Uyuşmazlık Mahkemesi", "Whitelist", "Görev uyuşmazlıkları için resmî kaynak."],
  ];
  els.officialSourceCount.textContent = String(sources.length);
  els.officialSourcesOutput.className = "result-list";
  els.officialSourcesOutput.innerHTML = `
    <div class="result-item">
      <h3>Resmî Kaynak Takibi</h3>
      <div class="meta-row">
        <span class="chip blue">Durum: Hazırlık aşamasında</span>
        <span class="chip">Canlı tarama: Kapalı</span>
        <span class="chip">Whitelist: Aktif</span>
        <span class="chip">Rastgele web taraması: Kapalı</span>
      </div>
      <ol class="compact-list">
        <li>Son kontrol: Henüz yapılmadı.</li>
        <li>Yeni kaynak: Yok.</li>
        <li>Rastgele blog, forum, haber sitesi veya izinsiz/telifli doktrin kazıması yapılmaz.</li>
      </ol>
    </div>
    ${sources
      .map(
        ([name, status, note]) => `
          <div class="result-item">
            <h3>${escapeHtml(name)}</h3>
            <div class="meta-row"><span class="chip blue">${escapeHtml(status)}</span><span class="chip">Doğrulama gerekli</span></div>
            <p>${escapeHtml(note)}</p>
          </div>
        `,
      )
      .join("")}
  `;
}

function currentDraftText() {
  const text = els.draftOutput.textContent.trim();
  if (!text || plainText(text).includes("henuz dilekce taslagi yok") || plainText(text).includes("analiz tamamlandiysa")) {
    throw new Error("Önce dilekçe taslağı oluşturmalısın.");
  }
  if (!text || text === "Henüz dilekçe taslağı yok.") {
    throw new Error("Önce dilekçe taslağı oluşturmalısın.");
  }
  return text;
}

async function runAnalysis() {
  const caseText = assertCaseText();
  setBusy(true, "Analiz yapılıyor...");
  try {
    const data = await apiPost("/case/analyze", {
      case_text: caseText,
      enriched_case_text: lastCaseEnrichment?.enriched_case_text || null,
    });
    setCaseState(data.case_state || null);
    renderAnalysis(data);
    setStatus("Analiz tamamlandı.");
    return data;
  } finally {
    setBusy(false);
  }
}

async function runAIEnrich() {
  const caseText = assertCaseText();
  setBusy(true, "AI olayı netleştiriyor...");
  try {
    const data = await apiPost("/ai/enrich-case", {
      case_text: caseText,
      practice_area: getPracticeArea() || "auto",
      use_gemini: false,
    });
    renderAIEnrichment(data);
    setStatus("Yerel olay analizi hazır.");
    return data;
  } finally {
    setBusy(false);
  }
}

async function runAIQuestions() {
  const caseText = assertCaseText();
  setBusy(true, "AI soruları üretiyor...");
  try {
    const data = await apiPost("/ai/generate-legal-questions", {
      case_text: caseText,
      case_enrichment: lastCaseEnrichment || {},
      use_gemini: false,
    });
    const questions = [...(data.questions || []).map((item) => item.question), ...documentMissingQuestions()];
    lastStrategy = {
      petition_type: lastCaseEnrichment?.detected_case_type || "AI soruları",
      legal_basis: lastCaseEnrichment?.relevant_articles || [],
      missing_information_questions: questions,
    };
    renderStrategy(lastStrategy);
    renderQuestionFields(questions);
    prefillQuestionsFromDocuments();
    await refreshCaseState();
    lastStrategyCase = caseText;
    lastStrategyRequest = getRequestType();
    setStatus(`${questions.length} yerel soru hazır.`);
    return data;
  } finally {
    setBusy(false);
  }
}

async function runAISearch() {
  const caseText = assertCaseText();
  setBusy(true, "AI arama sorguları hazırlanıyor...");
  try {
    const data = await apiPost("/ai/build-better-searches", {
      case_text: caseText,
      case_enrichment: lastCaseEnrichment || {},
      use_gemini: false,
    });
    renderAISearch(data);
    setStatus("Yerel arama sorguları hazır.");
    return data;
  } finally {
    setBusy(false);
  }
}

async function runBrain() {
  const caseText = assertCaseText();
  setBusy(true, "Legal Brain aranıyor...");
  try {
    const data = await apiPost("/legal-brain/search", {
      query: lastBetterSearches?.legal_brain_query || lastCaseEnrichment?.legal_brain_query || `${caseText} ${getRequestType()}`,
      practice_area: getPracticeArea(),
      max_results: getMaxResults(),
    });
    renderBrain(data);
    setStatus("Legal Brain sonuçları hazır.");
    return data;
  } catch (error) {
    const fallback = {
      results: [],
      warnings: ["Emsal/kaynak araması sırasında hata oluştu. Sistem yerel analizle devam etti."],
    };
    fallback.warnings = ["Kaynak araması yapılamadı; emsal denetimi yerel verilerle sürdürüldü."];
    renderBrain(fallback);
    setStatus(fallback.warnings[0], true);
    return fallback;
  } finally {
    setBusy(false);
  }
}

async function runAuditSources() {
  if (!lastBrainResults.length) {
    await runBrain();
  }
  setBusy(true, "Kaynaklar denetleniyor...");
  try {
    const audit = await apiPost("/ai/audit-sources", {
      case_enrichment: lastCaseEnrichment || { original_case_text: getCaseText(), detected_case_type: getCaseText() },
      sources: lastBrainResults,
      use_gemini: false,
    });
    const auditMap = new Map((audit.audited_sources || []).map((item) => [item.source_id, item]));
    const auditedResults = lastBrainResults
      .map((source, index) => {
        const sourceId = source.source_id || source.citation_label || source.title || `source_${index + 1}`;
        const item = auditMap.get(sourceId);
        return item
          ? {
              ...source,
              is_directly_relevant: item.is_directly_relevant,
              relevance_score: item.relevance_score,
              relevance_reason: item.reason || item.source_rejected_reason,
              usable_argument: item.use_in_petition ? source.usable_argument : UNRELATED_ARGUMENT,
              use_in_petition: item.use_in_petition,
            }
          : source;
      })
      .sort((a, b) => Number(Boolean(b.is_directly_relevant)) - Number(Boolean(a.is_directly_relevant)));
    renderBrain({ results: auditedResults, warnings: audit.warnings || [] });
    renderRisks({ sourceAudit: audit });
    setStatus("Kaynak denetimi tamamlandı.");
    return audit;
  } finally {
    setBusy(false);
  }
}

async function runYargitay() {
  const caseText = assertCaseText();
  setBusy(true, "Yargıtay kararları aranıyor...");
  try {
    const data = await apiPost("/research/yargitay", {
      case_text: `${caseText} ${getRequestType()}`,
      max_results: getMaxResults(),
      yargitay_query_templates: lastBetterSearches?.yargitay_queries || lastCaseEnrichment?.yargitay_query_templates || [],
      case_enrichment: { ...(lastCaseEnrichment || {}), fallback_precedent_candidates: legalBrainFallbackCandidates() },
    });
    renderAnalysis(data.case_analysis || {});
    renderDecisions(data);
    const errorSuffix = data.errors?.length ? ` ${data.errors.length} uyarı var.` : "";
    setStatus(`Yargıtay taraması tamamlandı.${errorSuffix}`);
    return data;
  } finally {
    setBusy(false);
  }
}

async function runAuditPrecedents() {
  if (!lastDecisions.length) {
    await runYargitay();
  }
  setBusy(true, "Emsaller denetleniyor...");
  try {
    const audit = await apiPost("/ai/audit-precedents", {
      case_text: getCaseText(),
      case_enrichment: lastCaseEnrichment || {},
      precedents: lastDecisions,
      use_gemini: false,
    });
    const auditMap = new Map((audit.audited_precedents || []).map((item) => [plainText(item.decision_id), item]));
    lastDecisions = lastDecisions
      .map((decision) => {
        const item = auditItemForDecision(auditMap, decision);
        return item
          ? {
              ...decision,
              lehe_aleyhe: item.alignment,
              usefulness_score: item.use_in_petition ? decision.usefulness_score || "Orta" : "Düşük",
              use_in_petition: item.use_in_petition,
              petition_paragraph: cleanOutputText(
                item.petition_usage_paragraph || decision.petition_paragraph,
                item.alignment === "riskli" || item.alignment === "aleyhe" ? RISK_PRECEDENT_PARAGRAPH : DEFAULT_PRECEDENT_PARAGRAPH,
              ),
              _is_duplicate: item.is_duplicate,
            }
          : decision;
      })
      .filter((decision) => !decision._is_duplicate);
    renderDecisions({ ...(lastYargitaySearch || {}), top_decisions: lastDecisions });
    renderRisks({ precedentAudit: audit });
    setStatus("Emsal denetimi tamamlandı.");
    return audit;
  } finally {
    setBusy(false);
  }
}

function mapStrategyDecisions() {
  return draftableDecisions(5).map((item) => ({
    similarity_score: item.similarity_score ?? 0,
    usefulness_score: item.usefulness_score || "orta",
    court: item.court || "Yargıtay",
    esas_no: item.esas_no || "-",
    karar_no: item.karar_no || "-",
    date: item.date || "-",
    short_summary: item.short_summary || "-",
    legal_principle: item.legal_principle || "-",
    why_relevant: item.why_relevant || "-",
    lehe_aleyhe: item.lehe_aleyhe || "Nötr",
    petition_paragraph: cleanDecisionParagraph(item),
  }));
}

function mapSelectedDecisions() {
  return draftableDecisions(3).map((item) => ({
    court: item.court || "Yargıtay",
    esas_no: item.esas_no || "-",
    karar_no: item.karar_no || "-",
    date: item.date || "-",
    petition_paragraph: cleanDecisionParagraph(item),
  }));
}

function mapPrecedentForPetition(limit = 5) {
  const livePreferred = (lastDecisions || []).filter((item) =>
    item.use_in_petition !== false
    && 
    (item.source_type || "") === "yargitay_live"
    && (item.official_verification_status || "") === "verified_live"
    && ["direct_support", "supporting_with_caution"].includes(decisionUseClass(item)),
  );
  return livePreferred.slice(0, limit).map((item) => ({
    court: item.court || "Yargıtay",
    chamber: item.court || "Yargıtay",
    esas_no: item.esas_no || "-",
    karar_no: item.karar_no || "-",
    date: item.date || "-",
    title: item.title || "",
    summary: cleanOutputText(item.short_summary || item.petition_use_summary || item.petition_paragraph || "", DEFAULT_PRECEDENT_PARAGRAPH),
    relevance: item.why_relevant || item.petition_use_summary || cleanDecisionParagraph(item),
    supported_issue: item.legal_principle || item.petition_use_summary || cleanDecisionParagraph(item),
    use_class: decisionUseClass(item),
    source_type: item.source_type || "unknown",
    official_verification_status: item.official_verification_status || "not_verified",
    petition_use_summary: item.petition_use_summary || cleanDecisionParagraph(item),
  }));
}

function draftableDecisions(limit = 3) {
  const preferred = lastDecisions.filter(decisionUsableForDraft);
  const fallback = lastDecisions.filter(decisionSafeForDraft);
  return (preferred.length ? preferred : fallback).slice(0, limit);
}

function decisionUsableForDraft(item) {
  if (item.use_in_petition === false) return false;
  const useClass = decisionUseClass(item);
  if (!["direct_support", "supporting_with_caution"].includes(useClass)) return false;
  const verification = plainText(`${item.verification_status || ""}`);
  const alignment = plainText(`${item.lehe_aleyhe || ""} ${item.petition_paragraph || ""}`);
  if (verification.includes("adverse_or_distinguishable_precedent") || alignment.includes("riskli") || alignment.includes("aleyhe")) {
    return false;
  }
  if (!verification.includes("verified_supportive_precedent")) return false;
  const usefulness = plainText(item.usefulness_score || "");
  return Number(item.similarity_score ?? 0) >= 50 && !usefulness.includes("dusuk");
}

function decisionSafeForDraft(item) {
  if (item.use_in_petition === false) return false;
  if (["procedural_or_jurisdiction_only", "insufficient_summary", "distinguishable", "exclude_from_petition"].includes(decisionUseClass(item))) return false;
  const verification = plainText(`${item.verification_status || ""}`);
  const alignment = plainText(`${item.lehe_aleyhe || ""} ${item.usefulness_score || ""} ${item.petition_paragraph || ""}`);
  if (verification.includes("adverse_or_distinguishable_precedent") || alignment.includes("riskli") || alignment.includes("aleyhe") || alignment.includes("dusuk")) return false;
  return Number(item.similarity_score ?? 0) >= 35;
}

function decisionAuditKeys(decision) {
  return [
    [decision.court || "Yargıtay", decision.esas_no || "", decision.karar_no || "", decision.date || ""].join(" | "),
    `${decision.court || "Yargıtay"}, E. ${decision.esas_no || ""}, K. ${decision.karar_no || ""}, T. ${decision.date || ""}`,
    [decision.court || "Yargıtay", decision.esas_no || "", decision.karar_no || "", decision.date || ""].join(" "),
  ].map((value) => plainText(value));
}

function auditItemForDecision(auditMap, decision) {
  for (const key of decisionAuditKeys(decision)) {
    if (auditMap.has(key)) return auditMap.get(key);
  }
  return null;
}

async function prepareQuestions(force = false) {
  const caseText = assertCaseText();
  if (!force && questionsAreCurrent()) {
    return lastStrategy;
  }
  setBusy(true, "Dilekçe soruları hazırlanıyor...");
  try {
    const data = await apiPost("/petition/strategy", {
      case_text: `${caseText} ${getRequestType()}`,
      top_decisions: mapStrategyDecisions(),
    });
    applyProfileRequestDefault(data);
    renderStrategy(data);
    renderQuestionFields([...(data.missing_information_questions || []), ...documentMissingQuestions()]);
    prefillQuestionsFromDocuments();
    await refreshCaseState();
    lastStrategyCase = caseText;
    lastStrategyRequest = getRequestType();
    setStatus("Sorular hazır. Cevapları doldurup Dilekçe'ye tekrar bas.");
    return data;
  } finally {
    setBusy(false);
  }
}

async function runDraft(options = {}) {
  const caseText = assertCaseText();
  answerCurrentQuestion();
  assertDocumentFlowReady();
  if (!options.force && !questionsAreCurrent()) {
    await prepareQuestions(false);
    return;
  }

  updateFinalPetitionReadiness();

  const unresolvedMissingFacts = dedupeIssues([
    ...(lastCaseEnrichment?.missing_facts || []),
    ...documentMissingFields(),
  ].filter((item) => !missingItemResolvedByDocuments(item))).slice(0, 30);

  setBusy(true, "Dilekçe taslağı hazırlanıyor...");
  try {
    const data = await apiPost("/petition/final-draft", {
      case_text: caseText,
      case_enrichment: {
        ...(lastCaseEnrichment || {}),
        final_precedents: (lastYargitaySearch?.final_precedents || lastDecisions || []).slice(0, 10),
        live_yargitay_results: (lastYargitaySearch?.live_yargitay_results || []).slice(0, 10),
      },
      confirmed_facts: [...new Set(lastCaseEnrichment?.confirmed_facts || [])].slice(0, 30),
      missing_facts: unresolvedMissingFacts,
      document_ids: (lastDocumentAnalysis?.documents || []).map((documentItem) => documentItem.document_id),
      document_facts: documentFactPayload(),
      petition_strategy_hint: lastCaseEnrichment?.petition_strategy_hint || "",
      answers: buildAnswers(),
      selected_decisions: mapSelectedDecisions(),
      precedent_for_petition: mapPrecedentForPetition(),
      precedent_candidates: lastDecisions,
      request_type: getRequestType(),
      use_legal_brain: true,
      legal_language_level: "usta_avukat",
      writer_mode: options.writer_mode === "gemini" ? "gemini" : "local",
      analysis_approved: els.documentApproval.checked,
      review_completed: reviewWorkflowComplete,
      legal_grounds: lastStrategy?.legal_basis || [],
      drafting_warnings: dedupeIssues([
        ...(lastCaseEnrichment?.risk_flags || []),
        ...(lastDocumentAnalysis?.warnings || []),
      ]).slice(0, 50),
    });
    lastDraftData = data;
    setCaseState(data.case_state || null);
    renderDraft(data);
    let draftAudit = null;
    if (options.auditAndRefine) {
      setStatus("Dilekçe kalite kontrolü yapılıyor...");
      draftAudit = await apiPost("/ai/audit-draft", {
        case_text: caseText,
        draft_text: currentDraftText(),
        case_enrichment: lastCaseEnrichment || {},
        selected_decisions: mapSelectedDecisions(),
        use_gemini: false,
      });
      lastDraftAudit = draftAudit;
      renderDraftAudit(draftAudit);

      if (draftAudit.can_refine && !(draftAudit.critical_issues || []).length) {
        setStatus("Usta avukat redaksiyonu deneniyor...");
        const refined = await apiPost("/ai/refine-draft", {
          case_text: caseText,
          draft_text: currentDraftText(),
          case_enrichment: lastCaseEnrichment || {},
          selected_decisions: mapSelectedDecisions(),
          use_gemini: false,
        });
        if (refined.refined_draft && refined.accepted) {
          els.draftOutput.textContent = refined.refined_draft;
        }
      } else {
        setStatus("Kritik uyarı nedeniyle redaksiyon atlandı.");
      }
    }
    renderStrategyToolkit();
    renderRisks({
      caseEnrichment: lastCaseEnrichment,
      sourceAudit: lastSourceAudit,
      precedentAudit: lastPrecedentAudit,
      draftAudit: draftAudit || lastDraftAudit,
      draftWarnings: data.warnings || [],
      draftGrounding: [],
    });
    switchTab("petition");
    const modeLabel = data.generation_mode === "gemini_mode" ? "Gemini" : "yerel güvenli şablon";
    if (options.writer_mode === "gemini" && data.generation_mode !== "gemini_mode" && data.fallback_used) {
      const reason = data.gemini_failure_reason || data.fallback_reason || "";
      const message = reason === "missing_api_key"
        ? "Gemini API anahtarı tanımlı değil; güvenli yerel taslak oluşturuldu."
        : reason === "timeout"
          ? "Gemini yanıtı zamanında alınamadı; güvenli yerel taslak oluşturuldu."
          : reason === "validation_failed" || reason === "technical_leakage_detected" || reason === "blocked_response"
            ? "Gemini çıktısı güvenlik kontrolünü geçmedi; güvenli yerel taslak oluşturuldu."
            : reason === "empty_response"
              ? "Gemini boş yanıt döndürdü; güvenli yerel taslak oluşturuldu."
              : "Gemini yanıtı alınamadı; güvenli yerel taslak oluşturuldu.";
      setStatus(message);
    } else {
      setStatus(`Nihai dilekçe taslağı ${modeLabel} ile hazırlandı.`);
    }
    return data;
  } finally {
    setBusy(false);
  }
}

async function runAuditDraft() {
  const draftText = currentDraftText();
  setBusy(true, "Dilekçe kalite kontrolü yapılıyor...");
  try {
    const data = await apiPost("/ai/audit-draft", {
      case_text: getCaseText(),
      draft_text: draftText,
      case_enrichment: lastCaseEnrichment || {},
      selected_decisions: mapSelectedDecisions(),
      use_gemini: false,
    });
    renderDraftAudit(data);
    setStatus(`Kalite kontrol tamamlandı: ${data.quality_score} puan.`);
    return data;
  } finally {
    setBusy(false);
  }
}

async function runRefineDraft() {
  const draftText = currentDraftText();
  setBusy(true, "Usta avukat redaksiyonu hazırlanıyor...");
  try {
    const data = await apiPost("/ai/refine-draft", {
      case_text: getCaseText(),
      draft_text: draftText,
      case_enrichment: lastCaseEnrichment || {},
      selected_decisions: mapSelectedDecisions(),
      use_gemini: false,
    });
    if (data.refined_draft) {
      els.draftOutput.textContent = data.refined_draft;
    }
    const warningSuffix = data.validator_warnings?.length ? ` ${data.validator_warnings.length} validator uyarısı var.` : "";
    setStatus(data.accepted ? `Redaksiyon hazır.${warningSuffix}` : `Redaksiyon validator’dan geçmedi; güvenli metin gösterildi.${warningSuffix}`, !data.accepted);
    return data;
  } finally {
    setBusy(false);
  }
}

function generateRequestId() {
  return "req-" + crypto.randomUUID();
}

async function runFullReview() {
  const caseText = assertCaseText();
  reviewWorkflowComplete = false;
  lastBetterSearches = null;
  lastSourceAudit = null;
  lastPrecedentAudit = null;

  setBusy(true, "İnceleme başlatılıyor...");
  switchTab("summary");

  try {
    const requestId = generateRequestId();
    setStatus("1/3 Olay ve hukuki meseleler analiz ediliyor...");

    const workflow = await apiPost("/workflow/review", {
      case_id: activeCaseId,
      request_id: requestId,
      case_text: caseText,
      practice_area: getPracticeArea() || "auto",
      max_yargitay_results: getMaxResults(),
      use_ai: true,
      use_legal_brain: true,
    }, { timeoutMs: 120_000 });

    if (workflow.cached) {
      setStatus("Önceki inceleme sonucu kullanıldı.");
    }

    if (workflow.status === "failed") {
      const stepErrors = workflow.steps
        .filter((s) => s.status === "failed")
        .map((s) => s.safe_error_message || s.name)
        .join(", ");
      throw new Error("İnceleme tamamlanamadı: " + (stepErrors || "kritik adım başarısız"));
    }

    if (workflow.status === "partial_success") {
      setStatus("Bazı adımlar tamamlanamadı. Mevcut sonuçlarla devam ediliyor.");
    }

    // ── Map workflow response to frontend state ──

    const analysis = {
      legal_topic: workflow.analysis.legal_topic || "",
      legal_keywords: workflow.analysis.legal_keywords || [],
      case_facts: workflow.analysis.case_facts || [],
      case_state: workflow.enrichment || {},
    };
    setCaseState(analysis.case_state || null);
    renderAnalysis(analysis);

    lastCaseEnrichment = workflow.enrichment || {};
    renderAIEnrichment(lastCaseEnrichment);
    renderRisks({ caseEnrichment: lastCaseEnrichment });

    const questions = (workflow.questions.questions || []).map((item) => item.question || item);
    const allQuestions = [...questions, ...documentMissingQuestions()];
    lastStrategy = {
      petition_type: lastCaseEnrichment.detected_case_type || "Dilekçe",
      legal_basis: lastCaseEnrichment.relevant_articles || [],
      missing_information_questions: allQuestions,
    };
    applyProfileRequestDefault(lastStrategy);
    renderStrategy(lastStrategy);
    renderQuestionFields(allQuestions);
    prefillQuestionsFromDocuments();
    lastStrategyCase = caseText;
    lastStrategyRequest = getRequestType();

    lastBetterSearches = workflow.better_searches || {};

    // Legal Brain results
    lastBrainResults = workflow.legal_brain_results || [];
    const sourceAudit = workflow.source_audit || {};
    if (sourceAudit.audited_sources) {
      lastSourceAudit = sourceAudit;
      const auditMap = new Map((sourceAudit.audited_sources || []).map((item) => [item.source_id, item]));
      const auditedSources = lastBrainResults.map((source, index) => {
        const sourceId = source.source_id || source.citation_label || source.title || "source_" + (index + 1);
        const item = auditMap.get(sourceId);
        return item
          ? { ...source, is_directly_relevant: item.is_directly_relevant, relevance_score: item.relevance_score,
              relevance_reason: item.reason || item.source_rejected_reason,
              usable_argument: item.use_in_petition ? source.usable_argument : UNRELATED_ARGUMENT,
              use_in_petition: item.use_in_petition }
          : source;
      }).sort((a, b) => Number(Boolean(b.is_directly_relevant)) - Number(Boolean(a.is_directly_relevant)));
      renderBrain({ results: auditedSources, warnings: sourceAudit.warnings || [] });
    } else {
      renderBrain({ results: lastBrainResults });
    }
    renderRisks({ caseEnrichment: lastCaseEnrichment, sourceAudit });

    // Yargıtay / Precedents
    const yargitay = workflow.yargitay_results || {};
    lastYargitaySearch = yargitay;
    lastDecisions = yargitay.final_precedents || [];

    // ── P0.5.1: Map canonical authority to decisions ──
    const authority = workflow.precedent_authority || {};
    const authorityRecords = authority.records || [];
    if (authorityRecords.length) {
      const authorityMap = {};
      authorityRecords.forEach((rec) => {
        const key = plainText([rec.court, rec.docket_number, rec.decision_number, rec.decision_date].join(" "));
        authorityMap[key] = rec;
      });
      lastDecisions = lastDecisions.map((d) => {
        const dk = plainText([d.court, d.esas_no, d.karar_no, d.date].join(" "));
        const rec = authorityMap[dk];
        if (rec) {
          return {
            ...d,
            _authority_status: rec.authority_status,
            _verification_status: rec.verification_status,
            _relevance_status: rec.relevance_status,
            _selection_status: rec.selection_status,
            _duplicate_status: rec.duplicate_status,
            _source_type: rec.source_type,
            _precedent_id: rec.precedent_id,
            _is_fallback: rec.authority_status === "fallback_only",
            _warnings: rec.warnings || [],
          };
        }
        return d;
      });
    }
    renderDecisions(yargitay);

    // Precedent audit
    const precedentAudit = workflow.precedent_audit || {};
    if (precedentAudit.audited_precedents) {
      lastPrecedentAudit = precedentAudit;
      const auditMap = new Map((precedentAudit.audited_precedents || []).map((item) => [plainText(item.decision_id), item]));
      lastDecisions = lastDecisions.map((decision) => {
        const item = auditItemForDecision(auditMap, decision);
        return item
          ? { ...decision, lehe_aleyhe: item.alignment,
              usefulness_score: item.use_in_petition ? decision.usefulness_score || "Orta" : "Düşük",
              use_in_petition: item.use_in_petition,
              petition_paragraph: cleanOutputText(item.petition_usage_paragraph || decision.petition_paragraph,
                item.alignment === "riskli" || item.alignment === "aleyhe" ? RISK_PRECEDENT_PARAGRAPH : DEFAULT_PRECEDENT_PARAGRAPH),
              _is_duplicate: item.is_duplicate }
          : decision;
      }).filter((d) => !d._is_duplicate);
      renderDecisions({ ...yargitay, top_decisions: lastDecisions });
      renderRisks({ caseEnrichment: lastCaseEnrichment, sourceAudit, precedentAudit });
    }

    renderStrategyToolkit();
    renderReviewSummary({
      analysis,
      enrichment: lastCaseEnrichment,
      sourceCount: lastBrainResults.length,
      precedentCount: lastDecisions.length,
      qualityScore: null,
    });

    // Legal Issue Graph
    if (workflow.issue_graph && workflow.issue_graph.issues) {
      lastLegalIssueGraph = workflow.issue_graph;
      renderLegalIssueGraph();
      renderRisks({ caseEnrichment: lastCaseEnrichment, sourceAudit, precedentAudit });
    } else {
      fetchLegalIssueGraph();
    }

    reviewWorkflowComplete = true;
    updateFinalPetitionReadiness();
    switchTab("summary");

    const warnings = workflow.warnings || [];
    const warningText = warnings.length ? " (" + warnings.length + " uyarı)" : "";
    setStatus("Kaynak ve emsal incelemesi hazır" + warningText + ". Soru kartlarını cevaplayıp Dilekçeyi Hazırla'ya bas.");
  } catch (error) {
    setStatus(error.message || "İnceleme sırasında hata oluştu.", true);
  } finally {
    setBusy(false);
  }
}

async function copyDraft() {
  const text = els.draftOutput.textContent.trim();
  if (!text || plainText(text).includes("analiz tamamlandiysa")) return;
  await navigator.clipboard.writeText(text);
  setStatus("Taslak panoya kopyalandı.");
}

function downloadDraft() {
  const text = els.draftOutput.textContent.trim();
  if (!text || plainText(text).includes("analiz tamamlandiysa")) return;
  const blob = new Blob([text], { type: "text/plain;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = "dilekce-taslagi.txt";
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

function downloadBlob(filename, content, type) {
  const blob = new Blob([content], { type });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

function printDraft() {
  const text = currentDraftText();
  const printWindow = window.open("", "_blank");
  if (!printWindow) {
    setStatus("Yazdırma penceresi açılamadı.", true);
    return;
  }
  printWindow.document.write(`<!doctype html><html><head><meta charset="utf-8"><title>Dilekçe</title><style>body{background:#f3f4f6;margin:0;padding:24px;font-family:Georgia,'Times New Roman',serif}.page{width:210mm;min-height:297mm;margin:auto;background:white;padding:25mm 22mm;box-shadow:0 0 0 1px #ddd;white-space:pre-wrap;line-height:1.6;color:#111827}@media print{body{background:white;padding:0}.page{box-shadow:none;margin:0;width:auto;min-height:auto}}</style></head><body><div class="page">${escapeHtml(text)}</div></body></html>`);
  printWindow.document.close();
  printWindow.focus();
  printWindow.print();
}

function downloadDocx() {
  const text = currentDraftText();
  const html = `<!doctype html><html><head><meta charset="utf-8"><title>Dilekçe</title></head><body><pre style="font-family:Georgia,'Times New Roman',serif;white-space:pre-wrap;line-height:1.6">${escapeHtml(text)}</pre></body></html>`;
  downloadBlob("dilekce-taslagi.doc", html, "application/msword;charset=utf-8");
  setStatus("Word uyumlu DOC çıktısı hazırlandı; DOCX servis modülü için altyapı ayrıldı.");
}

function downloadPdf() {
  printDraft();
  setStatus("PDF için yazdır penceresinde 'PDF olarak kaydet' seçilebilir.");
}

function downloadUdf() {
  const text = currentDraftText();
  const udf = `<?xml version="1.0" encoding="UTF-8"?>\n<emsalist-udf-placeholder>\n  <type>dilekce</type>\n  <note>UYAP UDF üretim modülü için placeholder çıktıdır.</note>\n  <content><![CDATA[${text}]]></content>\n</emsalist-udf-placeholder>\n`;
  downloadBlob("dilekce-udf-placeholder.xml", udf, "application/xml;charset=utf-8");
}

async function copyClientQuestions() {
  const text = (els.clientQuestionsOutput.innerText || "").trim();
  if (!text) return;
  await navigator.clipboard.writeText(text);
  setStatus("Müvekkil soru listesi panoya kopyalandı.");
}

function clearAll() {
  els.caseText.value = "";
  els.requestType.value = "Talebimizin kabulü";
  lastDecisions = [];
  lastBrainResults = [];
  lastCaseEnrichment = null;
  lastBetterSearches = null;
  lastYargitaySearch = null;
  lastDraftData = null;
  lastDraftAudit = null;
  lastSourceAudit = null;
  lastPrecedentAudit = null;
  reviewWorkflowComplete = false;
  lastDocumentAnalysis = null;
  selectedDocumentFiles = [];
  els.documentFiles.value = "";
  els.documentApproval.checked = false;
  resetQuestions();
  els.analysisCount.textContent = "0";
  els.brainCount.textContent = "0";
  els.decisionCount.textContent = "0";
  els.riskCount.textContent = "0";
  els.strategyCount.textContent = "0";
  els.defenseCount.textContent = "0";
  els.officialSourceCount.textContent = "0";
  els.analysisOutput.className = "empty-state";
  els.brainOutput.className = "empty-state";
  els.decisionOutput.className = "empty-state";
  els.riskOutput.className = "empty-state";
  els.strategyTabOutput.className = "empty-state";
  els.clientQuestionsOutput.className = "empty-state";
  els.defenseOutput.className = "empty-state";
  els.officialSourcesOutput.className = "empty-state";
  els.analysisOutput.textContent = "Henüz analiz yok.";
  els.brainOutput.textContent = "Henüz kaynak sonucu yok.";
  els.decisionOutput.textContent = "Henüz karar sonucu yok.";
  els.draftOutput.textContent = "Analiz tamamlandıysa “Dilekçe Taslağı Hazırla” butonuyla nihai taslak oluşturabilirsiniz.";
  els.riskOutput.textContent = "Henüz risk değerlendirmesi yok.";
  els.strategyTabOutput.textContent = "Henüz strateji hazırlanmadı.";
  els.clientQuestionsOutput.textContent = "Henüz müvekkil soru listesi yok.";
  els.defenseOutput.textContent = "Henüz savunma simülasyonu yok.";
  els.officialSourcesOutput.textContent = "Henüz resmî kaynak takibi yok.";
  switchTab("summary");
  renderDocuments();
  renderDocumentSelection();
  updateFinalPetitionReadiness();
  setStatus("");
}

async function startNewCase() {
  setBusy(true, "Yeni dosya oluÅŸturuluyor...");
  try {
    const data = await apiPost("/case/new", {});
    activeCaseId = data.case_id || null;
    renderActiveCaseBadge();
    clearAll();
    await loadDocuments();
    setCaseState(null);
    setStatus(data.message || "Yeni dosya baÅŸlatÄ±ldÄ±.");
  } finally {
    setBusy(false);
  }
}

async function checkHealth() {
  try {
    const response = await apiFetch("/health");
    if (!response.ok) throw new Error("health");
    els.healthPill.textContent = "API hazır";
    els.healthPill.className = "status-pill ok";
  } catch {
    els.healthPill.textContent = "API bağlantısı yok";
    els.healthPill.className = "status-pill bad";
  }
}

function updateApiLinks() {
  document.querySelectorAll("[data-api-link]").forEach((link) => {
    link.href = apiUrl(link.dataset.apiLink);
  });
}

function wireEvents() {
  ensureCaseControls();
  updateApiLinks();
  initTheme();
  els.themeToggle?.addEventListener("change", () => applyTheme(els.themeToggle.checked ? "dark" : "light"));
  document.querySelectorAll("[data-tab]").forEach((button) => {
    button.addEventListener("click", () => switchTab(button.dataset.tab));
  });
  els.questionFields.addEventListener("click", handleQuestionOptionClick);
  els.questionFields.addEventListener("input", (event) => {
    const field = event.target.closest("[data-question]");
    if (field) saveQuestionField(field);
    renderRisks();
    updateFinalPetitionReadiness();
  });
  els.analysisOutput.addEventListener("click", (event) => {
    const button = event.target.closest("[data-action='use-ai-enrichment']");
    if (!button || !lastCaseEnrichment) return;
    const enrichment = lastCaseEnrichment;
    if (enrichment.enriched_case_text) {
      setFieldValue(els.caseText, enrichment.enriched_case_text);
      lastCaseEnrichment = enrichment;
    }
    lastStrategy = {
      petition_type: enrichment.detected_case_type || "AI analiz",
      legal_basis: enrichment.relevant_articles || [],
      missing_information_questions: enrichment.critical_questions || [],
    };
    renderStrategy(lastStrategy);
    renderQuestionFields(enrichment.critical_questions || []);
    lastStrategyCase = getCaseText();
    lastStrategyRequest = getRequestType();
    setStatus("AI analizi aktif akışa alındı.");
  });
  els.documentFiles.addEventListener("change", () => {
    // Gerçek File objelerini state'te sakla
    selectedDocumentFiles = Array.from(els.documentFiles.files || []);
    renderDocumentSelection();
    if (selectedDocumentFiles.length) {
      setStatus(`${selectedDocumentFiles.length} dosya seçildi. Backend'e göndermek için Belgeleri Yükle'ye basın.`);
    }
  });
  $("uploadDocumentsBtn").addEventListener("click", () => uploadDocuments().catch((error) => setStatus(error.message, true)));
  $("analyzeDocumentsBtn").addEventListener("click", () => analyzeDocuments().catch((error) => setStatus(error.message, true)));
  els.documentOutput.addEventListener("click", (event) => {
    const button = event.target.closest("[data-delete-document]");
    if (!button) return;
    const documentId = button.dataset.deleteDocument;
    if (!window.confirm("Bu belgeyi kalıcı olarak silmek istiyor musunuz?")) return;
    deleteDocument(documentId).catch((error) => setStatus(error.message, true));
  });
  $("cancelPreliminaryDraftBtn").addEventListener("click", () => {
    pendingPreliminaryDraftOptions = null;
    els.draftReadinessDialog.close();
    setStatus("Dilekçe üretilmedi. Önce kritik bilgi, belge ve inceleme adımlarını tamamlayın.", true);
  });
  $("confirmPreliminaryDraftBtn").addEventListener("click", () => {
    const options = pendingPreliminaryDraftOptions;
    pendingPreliminaryDraftOptions = null;
    els.draftReadinessDialog.close();
    if (options) runDraft(options).catch((error) => setStatus(error.message, true));
  });
  $("legalMapRebuildBtn").addEventListener("click", () => rebuildLegalMap().catch((error) => setStatus(error.message, true)));
  $("legalMapValidateBtn").addEventListener("click", () => validateLegalMap().catch((error) => setStatus(error.message, true)));
  $("legalMapMissingBtn").addEventListener("click", () => {
    if (lastLegalMapValidation) { renderLegalMapMissing(lastLegalMapValidation); }
    else { validateLegalMap().catch((error) => setStatus(error.message, true)); }
  });
  $("legalMapAddNodeBtn").addEventListener("click", () => addLegalMapNode().catch((error) => setStatus(error.message, true)));
  els.draftReadinessDialog.addEventListener("cancel", (event) => {
    event.preventDefault();
    pendingPreliminaryDraftOptions = null;
    els.draftReadinessDialog.close();
    setStatus("Dilekçe üretilmedi. Önce kritik bilgi, belge ve inceleme adımlarını tamamlayın.", true);
  });
  $("reviewBtn").addEventListener("click", () => runFullReview().catch((error) => setStatus(error.message, true)));
  $("localDraftBtn").addEventListener("click", () => runDraft({ force: true, writer_mode: "local" }).catch((error) => setStatus(error.message, true)));
  $("aiDraftBtn")?.addEventListener("click", () => runDraft({ force: true, writer_mode: "gemini" }).catch((error) => setStatus(error.message, true)));
  $("aiEnrichBtn").addEventListener("click", () => runAIEnrich().catch((error) => setStatus(error.message, true)));
  $("aiQuestionsBtn").addEventListener("click", () => runAIQuestions().catch((error) => setStatus(error.message, true)));
  $("aiSearchBtn").addEventListener("click", () => runAISearch().catch((error) => setStatus(error.message, true)));
  $("analyzeBtn").addEventListener("click", () => runAnalysis().catch((error) => setStatus(error.message, true)));
  $("brainBtn").addEventListener("click", () => runBrain().catch((error) => setStatus(error.message, true)));
  $("auditSourcesBtn").addEventListener("click", () => runAuditSources().catch((error) => setStatus(error.message, true)));
  $("yargitayBtn").addEventListener("click", () => runYargitay().catch((error) => setStatus(error.message, true)));
  $("auditPrecedentsBtn").addEventListener("click", () => runAuditPrecedents().catch((error) => setStatus(error.message, true)));
  $("questionsBtn").addEventListener("click", () => prepareQuestions(true).catch((error) => setStatus(error.message, true)));
  $("draftBtn").addEventListener("click", () => runDraft().catch((error) => setStatus(error.message, true)));
  $("auditDraftBtn").addEventListener("click", () => runAuditDraft().catch((error) => setStatus(error.message, true)));
  $("refineDraftBtn").addEventListener("click", () => runRefineDraft().catch((error) => setStatus(error.message, true)));
  $("sampleBtn").addEventListener("click", () => {
    els.caseText.value =
      "Müvekkil, ikinci el aracı satıcının kazasız, ağır hasarsız ve sorunsuz olduğu yönündeki beyanlarına güvenerek noter satışıyla satın aldı. Teslimden kısa süre sonra araçta motor arızası ortaya çıktı; servis incelemesinde arızanın önceki onarım ve gizli hasar kaydıyla bağlantılı olabileceği bildirildi. Müvekkil durumu öğrenir öğrenmez satıcıya WhatsApp üzerinden bildirdi, ancak satıcı sorumluluk kabul etmedi. Sözleşmeden dönme ve satış bedelinin iadesi, aksi halde bedel indirimi ile servis, ekspertiz ve onarım giderlerinin tahsili istenmektedir.";
    els.practiceArea.value = "BorÃ§lar hukuku";
    els.requestType.value = "İhtiyaç nedeniyle kiralananın tahliyesine karar verilmesi";
    els.requestType.value = defectiveVehicleRequest;
    lastDecisions = [];
    resetQuestions();
    setStatus("Örnek olay yüklendi.");
  });
  $("clearBtn").addEventListener("click", clearAll);
  $("newCaseBtn")?.addEventListener("click", () => startNewCase().catch((error) => setStatus(error.message, true)));
  $("copyDraftBtn").addEventListener("click", () => copyDraft().catch((error) => setStatus(error.message, true)));
  $("downloadDraftBtn").addEventListener("click", downloadDraft);
  $("printDraftBtn")?.addEventListener("click", () => {
    try {
      printDraft();
    } catch (error) {
      setStatus(error.message, true);
    }
  });
  $("downloadDocxBtn")?.addEventListener("click", () => {
    try {
      downloadDocx();
    } catch (error) {
      setStatus(error.message, true);
    }
  });
  $("downloadPdfBtn")?.addEventListener("click", () => {
    try {
      downloadPdf();
    } catch (error) {
      setStatus(error.message, true);
    }
  });
  $("downloadUdfBtn")?.addEventListener("click", () => {
    try {
      downloadUdf();
    } catch (error) {
      setStatus(error.message, true);
    }
  });
  $("copyClientQuestionsBtn")?.addEventListener("click", () => copyClientQuestions().catch((error) => setStatus(error.message, true)));
  els.caseText.addEventListener("input", () => {
    lastStrategyCase = "";
    lastCaseEnrichment = null;
    lastBetterSearches = null;
    lastYargitaySearch = null;
    reviewWorkflowComplete = false;
  });
  els.requestType.addEventListener("input", () => {
    lastStrategyRequest = "";
    reviewWorkflowComplete = false;
  });
  els.documentApproval.addEventListener("change", updateFinalPetitionReadiness);
}

function ensureCaseControls() {
  const nav = document.querySelector(".top-actions");
  if (!nav) return;

  let badge = document.getElementById("activeCaseBadge");
  if (!badge) {
    badge = document.createElement("span");
    badge.id = "activeCaseBadge";
    badge.className = "status-pill";
    nav.insertBefore(badge, els.healthPill || null);
  }
  badge.textContent = activeCaseId ? `Aktif Dosya: ${activeCaseId}` : DEFAULT_ACTIVE_CASE_LOADING_LABEL;

  let button = document.getElementById("newCaseBtn");
  if (!button) {
    button = document.createElement("button");
    button.id = "newCaseBtn";
    button.type = "button";
    button.className = "ghost-btn";
    nav.insertBefore(button, els.healthPill || null);
  }
  button.textContent = DEFAULT_NEW_CASE_LABEL;
}

function renderActiveCaseBadge() {
  const badge = document.getElementById("activeCaseBadge");
  if (!badge) return;
  badge.textContent = activeCaseId ? `Aktif Dosya: ${activeCaseId}` : DEFAULT_ACTIVE_CASE_EMPTY_LABEL;
}

async function initializeCaseSession() {
  ensureCaseControls();
  const current = await apiFetch("/case/current");
  if (!current.ok) throw new Error("Aktif dosya bilgisi alınamadı.");
  const data = await current.json();
  activeCaseId = data.case_id || null;
  renderActiveCaseBadge();
}

function resetCaseUiState({ preserveCaseId = true, clearStatus = true } = {}) {
  if (!preserveCaseId) {
    activeCaseId = null;
  }

  els.caseText.value = "";
  els.practiceArea.value = "";
  els.maxResults.value = DEFAULT_MAX_RESULTS;
  els.requestType.value = DEFAULT_REQUEST_TYPE;

  lastDecisions = [];
  lastBrainResults = [];
  lastCaseEnrichment = null;
  lastBetterSearches = null;
  lastDraftData = null;
  lastDraftAudit = null;
  lastSourceAudit = null;
  lastPrecedentAudit = null;
  lastYargitaySearch = null;
  lastDocuments = [];
  lastDocumentAnalysis = null;
  reviewWorkflowComplete = false;
  pendingPreliminaryDraftOptions = null;
  selectedDocumentFiles = [];

  els.documentFiles.value = "";
  els.documentType.value = "";
  els.documentApproval.checked = false;
  els.draftReadinessIssues.innerHTML = "";
  if (els.draftReadinessDialog.open) {
    els.draftReadinessDialog.close();
  }

  lastLegalIssueGraph = null;
  renderLegalIssueGraph();

  clearLegalMapState();

  resetQuestions();
  setCaseState(null);

  els.analysisCount.textContent = "0";
  els.brainCount.textContent = "0";
  els.decisionCount.textContent = "0";
  els.riskCount.textContent = "0";
  els.strategyCount.textContent = "0";
  els.defenseCount.textContent = "0";
  els.officialSourceCount.textContent = "0";
  els.evidenceCount.textContent = "0";

  els.analysisOutput.className = "empty-state";
  els.analysisOutput.textContent = DEFAULT_ANALYSIS_EMPTY;
  els.brainOutput.className = "empty-state";
  els.brainOutput.textContent = DEFAULT_BRAIN_EMPTY;
  els.decisionOutput.className = "empty-state";
  els.decisionOutput.textContent = DEFAULT_DECISION_EMPTY;
  els.draftOutput.textContent = "";
  els.riskOutput.className = "empty-state";
  els.riskOutput.textContent = DEFAULT_RISK_EMPTY;
  els.strategyTabOutput.className = "empty-state";
  els.strategyTabOutput.textContent = DEFAULT_STRATEGY_EMPTY;
  els.clientQuestionsOutput.className = "empty-state";
  els.clientQuestionsOutput.textContent = DEFAULT_CLIENT_QUESTIONS_EMPTY;
  els.defenseOutput.className = "empty-state";
  els.defenseOutput.textContent = DEFAULT_DEFENSE_EMPTY;
  els.officialSourcesOutput.className = "empty-state";
  els.officialSourcesOutput.textContent = DEFAULT_OFFICIAL_SOURCES_EMPTY;
  els.evidenceOutput.className = "empty-state";
  els.evidenceOutput.textContent = DEFAULT_EVIDENCE_EMPTY;

  renderDocuments();
  renderDocumentSelection();
  updateFinalPetitionReadiness();
  switchTab("summary");
  renderActiveCaseBadge();

  if (clearStatus) {
    setStatus("");
  }
}

function clearAll() {
  resetCaseUiState({ preserveCaseId: true, clearStatus: true });
}

async function startNewCase() {
  setBusy(true, "Yeni dosya oluşturuluyor...");
  try {
    const data = await apiPost("/case/new", {});
    activeCaseId = data.case_id || activeCaseId;
    resetCaseUiState({ preserveCaseId: true, clearStatus: true });
    await loadDocuments();
    renderActiveCaseBadge();
    setStatus(DEFAULT_NEW_CASE_STATUS);
    return data;
  } finally {
    setBusy(false);
  }
}

// ── P1.8 Job Polling ──
let _jobPollTimers = {};
let _maxJobPollSeconds = 120;

async function trackJob(jobId, onComplete, onProgress) {
  if (!jobId) return;
  if (_jobPollTimers[jobId]) clearTimeout(_jobPollTimers[jobId]);
  let elapsed = 0;
  async function poll() {
    try {
      const job = await apiFetch(apiUrl(`/jobs/${jobId}`));
      const data = await job.json();
      if (onProgress) onProgress(data);
      if (data.status === "succeeded") {
        delete _jobPollTimers[jobId];
        if (onComplete) onComplete(data);
        return;
      }
      if (data.status === "failed" || data.status === "cancelled" || data.status === "dead_lettered") {
        delete _jobPollTimers[jobId];
        setStatus("Islem tamamlanamadi: " + (data.safe_error_code || data.status));
        return;
      }
      elapsed += 2;
      if (elapsed > _maxJobPollSeconds) {
        delete _jobPollTimers[jobId];
        setStatus("Islem zaman asimina ugradi.");
        return;
      }
      _jobPollTimers[jobId] = setTimeout(poll, 2000);
    } catch (e) {
      delete _jobPollTimers[jobId];
    }
  }
  poll();
}

function cancelTrackedJob(jobId) {
  if (_jobPollTimers[jobId]) {
    clearTimeout(_jobPollTimers[jobId]);
    delete _jobPollTimers[jobId];
  }
}

wireEvents();
renderOfficialSourcesStatus();
checkHealth();
initializeCaseSession()
  .then(() => {
    loadDocuments();
    fetchLegalIssueGraph();
  })
  .catch((error) => setStatus(error.message, true));
