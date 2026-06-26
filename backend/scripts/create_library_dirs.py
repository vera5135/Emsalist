import os

dirs = [
    'backend/app/legal_brain/library',
    'backend/app/legal_brain/library/statutes',
    'backend/app/legal_brain/library/statutes/TMK',
    'backend/app/legal_brain/library/statutes/TBK',
    'backend/app/legal_brain/library/statutes/HMK',
    'backend/app/legal_brain/library/statutes/IIK',
    'backend/app/legal_brain/library/statutes/TCK',
    'backend/app/legal_brain/library/statutes/CMK',
    'backend/app/legal_brain/library/statutes/TTK',
    'backend/app/legal_brain/library/statutes/IS_KANUNU',
    'backend/app/legal_brain/library/statutes/TKHK',
    'backend/app/legal_brain/library/statutes/KMK',
    'backend/app/legal_brain/library/statutes/IYUK',
    'backend/app/legal_brain/library/statutes/ARABULUCULUK',
    'backend/app/legal_brain/library/statutes/KVKK',
    'backend/app/legal_brain/library/regulations',
    'backend/app/legal_brain/library/official_gazette',
    'backend/app/legal_brain/library/yargitay',
    'backend/app/legal_brain/library/danistay',
    'backend/app/legal_brain/library/aym',
    'backend/app/legal_brain/library/baro_tbb',
    'backend/app/legal_brain/library/doctrine',
    'backend/app/legal_brain/library/petition_samples',
    'backend/app/legal_brain/library/practice_guides',
    'backend/app/legal_brain/library/user_verified_notes',
    'backend/app/legal_brain/library/unsorted',
    'backend/app/legal_brain/library/rejected',
    'backend/app/legal_brain/metadata'
]

for d in dirs:
    os.makedirs(d, exist_ok=True)
    print(f"Created: {d}")

print("Klasörler oluşturuldu")