# Precedent Label Policy v1

## verification_status

### verified
- Zorunlu: resmî Yargıtay kaynağından E/K/tarih doğrulanmış VEYA Legal Brain kaydı resmî kaynak kimliği taşıyor
- Yasak: AI önerisi, fallback, kaynak URL yok, E/K eksik

### partially_verified
- Zorunlu: E/K veya tarihten en az biri mevcut, kaynak URL var
- Yasak: AI üretimi E/K

### unverified
- Varsayılan: AI önerisi, fallback, Legal Brain kaydı ama resmî kimlik yok

### invalid
- Zorunlu: E/K formatı geçersiz, sahte URL, uydurulmuş karar numarası

## authority_status

### authoritative
- Zorunlu: verified + official_yargitay source + E/K tam

### persuasive
- Zorunlu: verified/partially_verified + kaynak kimliği var

### fallback_only
- Zorunlu: source_type deterministic_fallback VEYA AI önerisi VEYA kaynak yok

### prohibited
- Zorunlu: başka case_id, invalid verification, rejected + sticky

## relevance_status

### directly_relevant
- Zorunlu: aynı hukuki mesele + benzer olay yapısı + lehe karar

### partially_relevant
- Zorunlu: kısmi örtüşme, farklı daire, farklı olay ama aynı ilke

### irrelevant
- Zorunlu: farklı dava türü, taşınmaz/araç karışması, usul kararı

### insufficient_facts
- Zorunlu: gerekli vakıa eksik, karar verilemez

## selection_status

### accepted
- Zorunlu: verified/partially_verified + relevant + authoritative/persuasive + duplicate değil

### rejected
- Zorunlu: invalid VEYA irrelevant VEYA duplicate VEYA fallback_only VEYA prohibited

### used_in_petition
- Zorunlu: accepted + backend set when petition uses this precedent

## duplicate_status

### unique
- unique canonical_key

### duplicate
- same canonical_key as another record

### possible_duplicate
- same docket number, similar title, different canonical_key (format variation)
