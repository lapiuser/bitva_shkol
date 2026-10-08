from __future__ import annotations

from dataclasses import dataclass

@dataclass(frozen=True)
class SchoolSpec:
    id: str
    country: str
    region: str
    city: str
    category: str
    category_label: str
    name: str
    folder: str
    image_source: str = "bundled"

CATEGORY_ORDER = [
    "general_schools",
    "lyceums_gymnasiums",
    "colleges",
    "universities",
    "private_schools",
    "boarding_schools",
]
CATEGORY_LABELS = {
    "general_schools": "Общеобразовательные школы",
    "lyceums_gymnasiums": "Лицеи и гимназии",
    "colleges": "Колледжи и техникумы",
    "universities": "ВУЗы",
    "private_schools": "Частные школы",
    "boarding_schools": "Школы-интернаты",
}

# Эти школы уже входили в первую калининградскую версию. Их фотографии сохраняются.
SCHOOLS = [
    SchoolSpec('bfu_kant', 'Россия', 'Калининградская область', 'Калининград', 'universities', 'ВУЗы', 'БФУ им. И. Канта', 'bfu_kant', 'bundled'),
    SchoolSpec('kstu', 'Россия', 'Калининградская область', 'Калининград', 'universities', 'ВУЗы', 'КГТУ', 'kstu', 'bundled'),
    SchoolSpec('bgarf', 'Россия', 'Калининградская область', 'Калининград', 'universities', 'ВУЗы', 'БГАРФ', 'bgarf', 'bundled'),
    SchoolSpec('ranepa_west', 'Россия', 'Калининградская область', 'Калининград', 'universities', 'ВУЗы', 'Западный филиал РАНХиГС', 'ranepa_west', 'bundled'),
    SchoolSpec('mfua_kaliningrad', 'Россия', 'Калининградская область', 'Калининград', 'universities', 'ВУЗы', 'Калининградский филиал МФЮА', 'mfua_kaliningrad', 'bundled'),
    SchoolSpec('kaliningrad_institute_management', 'Россия', 'Калининградская область', 'Калининград', 'universities', 'ВУЗы', 'Калининградский институт управления', 'kaliningrad_institute_management', 'bundled'),
    SchoolSpec('mvd_university_kaliningrad', 'Россия', 'Калининградская область', 'Калининград', 'universities', 'ВУЗы', 'Калининградский филиал Санкт-Петербургского университета МВД России', 'mvd_university_kaliningrad', 'bundled'),
    SchoolSpec('naval_academy_kaliningrad', 'Россия', 'Калининградская область', 'Калининград', 'universities', 'ВУЗы', 'Калининградский филиал ВУНЦ ВМФ «Военно-морская академия»', 'naval_academy_kaliningrad', 'bundled'),
    SchoolSpec('rachmaninov_music_college', 'Россия', 'Калининградская область', 'Калининград', 'colleges', 'Колледжи и техникумы', 'Музыкальный колледж им. С.В. Рахманинова', 'rachmaninov_music_college', 'bundled'),
    SchoolSpec('marine_fishing_college', 'Россия', 'Калининградская область', 'Калининград', 'colleges', 'Колледжи и техникумы', 'Калининградский морской рыбопромышленный колледж', 'marine_fishing_college', 'bundled'),
    SchoolSpec('it_construction_college', 'Россия', 'Калининградская область', 'Калининград', 'colleges', 'Колледжи и техникумы', 'Колледж информационных технологий и строительства', 'it_construction_college', 'bundled'),
    SchoolSpec('business_college', 'Россия', 'Калининградская область', 'Калининград', 'colleges', 'Колледжи и техникумы', 'Бизнес-колледж', 'business_college', 'bundled'),
    SchoolSpec('entrepreneurship_college', 'Россия', 'Калининградская область', 'Калининград', 'colleges', 'Колледжи и техникумы', 'Колледж предпринимательства', 'entrepreneurship_college', 'bundled'),
    SchoolSpec('baltic_shipbuilding_technical_school', 'Россия', 'Калининградская область', 'Калининград', 'colleges', 'Колледжи и техникумы', 'Прибалтийский судостроительный техникум', 'baltic_shipbuilding_technical_school', 'bundled'),
    SchoolSpec('service_tourism_college', 'Россия', 'Калининградская область', 'Калининград', 'colleges', 'Колледжи и техникумы', 'Колледж сервиса и туризма', 'service_tourism_college', 'bundled'),
    SchoolSpec('culture_art_college', 'Россия', 'Калининградская область', 'Калининград', 'colleges', 'Колледжи и техникумы', 'Калининградский областной колледж культуры и искусства', 'culture_art_college', 'bundled'),
    SchoolSpec('agrotechnology_nature_college', 'Россия', 'Калининградская область', 'Калининград', 'colleges', 'Колледжи и техникумы', 'Колледж агротехнологий и природообустройства', 'agrotechnology_nature_college', 'bundled'),
    SchoolSpec('geodesy_cartography_college', 'Россия', 'Калининградская область', 'Калининград', 'colleges', 'Колледжи и техникумы', 'Калининградский филиал Санкт-Петербургского техникума геодезии и картографии', 'geodesy_cartography_college', 'bundled'),
    SchoolSpec('gymnasium_40', 'Россия', 'Калининградская область', 'Калининград', 'lyceums_gymnasiums', 'Лицеи и гимназии', 'Гимназия № 40 им. Ю. А. Гагарина', 'gymnasium_40', 'bundled'),
    SchoolSpec('lyceum_49', 'Россия', 'Калининградская область', 'Калининград', 'lyceums_gymnasiums', 'Лицеи и гимназии', 'Лицей № 49', 'lyceum_49', 'bundled'),
    SchoolSpec('lyceum_23', 'Россия', 'Калининградская область', 'Калининград', 'lyceums_gymnasiums', 'Лицеи и гимназии', 'Лицей № 23', 'lyceum_23', 'bundled'),
    SchoolSpec('lyceum_35', 'Россия', 'Калининградская область', 'Калининград', 'lyceums_gymnasiums', 'Лицеи и гимназии', 'Лицей № 35 им. Буткова В.В.', 'lyceum_35', 'bundled'),
    SchoolSpec('lyceum_17', 'Россия', 'Калининградская область', 'Калининград', 'lyceums_gymnasiums', 'Лицеи и гимназии', 'Лицей № 17', 'lyceum_17', 'bundled'),
    SchoolSpec('lyceum_18', 'Россия', 'Калининградская область', 'Калининград', 'lyceums_gymnasiums', 'Лицеи и гимназии', 'Лицей № 18', 'lyceum_18', 'bundled'),
    SchoolSpec('kaliningrad_marine_lyceum', 'Россия', 'Калининградская область', 'Калининград', 'lyceums_gymnasiums', 'Лицеи и гимназии', 'Калининградский Морской Лицей', 'kaliningrad_marine_lyceum', 'bundled'),
    SchoolSpec('shili', 'Россия', 'Калининградская область', 'Калининград', 'lyceums_gymnasiums', 'Лицеи и гимназии', 'Школа-интернат лицей-интернат (ШИЛИ)', 'shili', 'bundled'),
    SchoolSpec('gymnasium_32', 'Россия', 'Калининградская область', 'Калининград', 'lyceums_gymnasiums', 'Лицеи и гимназии', 'Гимназия № 32', 'gymnasium_32', 'bundled'),
    SchoolSpec('gymnasium_22', 'Россия', 'Калининградская область', 'Калининград', 'lyceums_gymnasiums', 'Лицеи и гимназии', 'Гимназия № 22', 'gymnasium_22', 'bundled'),
    SchoolSpec('gymnasium_1', 'Россия', 'Калининградская область', 'Калининград', 'lyceums_gymnasiums', 'Лицеи и гимназии', 'Гимназия № 1', 'gymnasium_1', 'bundled'),
    SchoolSpec('kadet_marine_corps', 'Россия', 'Калининградская область', 'Калининград', 'lyceums_gymnasiums', 'Лицеи и гимназии', 'Андрея Первозванного Кадетский морской корпус', 'kadet_marine_corps', 'bundled'),
    SchoolSpec('nakhimov_school_branch', 'Россия', 'Калининградская область', 'Калининград', 'lyceums_gymnasiums', 'Лицеи и гимназии', 'Филиал Нахимовского военно-морского училища', 'nakhimov_school_branch', 'bundled'),
    SchoolSpec('hanzean_ladya', 'Россия', 'Калининградская область', 'Калининград', 'private_schools', 'Частные школы', 'Лицей «Ганзейская Ладья»', 'hanzean_ladya', 'bundled'),
    SchoolSpec('orthodox_gymnasium', 'Россия', 'Калининградская область', 'Калининград', 'private_schools', 'Частные школы', 'Православная гимназия', 'orthodox_gymnasium', 'bundled'),
    SchoolSpec('albertina', 'Россия', 'Калининградская область', 'Калининград', 'private_schools', 'Частные школы', 'Альбертина', 'albertina', 'bundled'),
    SchoolSpec('dirigible', 'Россия', 'Калининградская область', 'Калининград', 'private_schools', 'Частные школы', 'Дирижабль', 'dirigible', 'bundled'),
    SchoolSpec('erudit', 'Россия', 'Калининградская область', 'Калининград', 'private_schools', 'Частные школы', 'Эрудит', 'erudit', 'bundled'),
    SchoolSpec('solnechny_luchik', 'Россия', 'Калининградская область', 'Калининград', 'private_schools', 'Частные школы', 'школа-детский сад «Солнечный лучик»', 'solnechny_luchik', 'bundled'),
    SchoolSpec('school_2', 'Россия', 'Калининградская область', 'Калининград', 'general_schools', 'Общеобразовательные школы', 'СОШ № 2', 'school_2', 'bundled'),
    SchoolSpec('school_3', 'Россия', 'Калининградская область', 'Калининград', 'general_schools', 'Общеобразовательные школы', 'СОШ № 3', 'school_3', 'bundled'),
    SchoolSpec('school_4', 'Россия', 'Калининградская область', 'Калининград', 'general_schools', 'Общеобразовательные школы', 'СОШ № 4', 'school_4', 'bundled'),
    SchoolSpec('school_5', 'Россия', 'Калининградская область', 'Калининград', 'general_schools', 'Общеобразовательные школы', 'СОШ № 5', 'school_5', 'bundled'),
    SchoolSpec('school_6', 'Россия', 'Калининградская область', 'Калининград', 'general_schools', 'Общеобразовательные школы', 'СОШ № 6', 'school_6', 'bundled'),
    SchoolSpec('school_7', 'Россия', 'Калининградская область', 'Калининград', 'general_schools', 'Общеобразовательные школы', 'СОШ № 7', 'school_7', 'bundled'),
    SchoolSpec('school_8', 'Россия', 'Калининградская область', 'Калининград', 'general_schools', 'Общеобразовательные школы', 'СОШ № 8', 'school_8', 'bundled'),
    SchoolSpec('school_9', 'Россия', 'Калининградская область', 'Калининград', 'general_schools', 'Общеобразовательные школы', 'СОШ № 9', 'school_9', 'bundled'),
    SchoolSpec('school_10', 'Россия', 'Калининградская область', 'Калининград', 'general_schools', 'Общеобразовательные школы', 'СОШ № 10', 'school_10', 'bundled'),
    SchoolSpec('school_11', 'Россия', 'Калининградская область', 'Калининград', 'general_schools', 'Общеобразовательные школы', 'СОШ № 11', 'school_11', 'bundled'),
    SchoolSpec('school_12', 'Россия', 'Калининградская область', 'Калининград', 'general_schools', 'Общеобразовательные школы', 'СОШ № 12', 'school_12', 'bundled'),
    SchoolSpec('school_13', 'Россия', 'Калининградская область', 'Калининград', 'general_schools', 'Общеобразовательные школы', 'СОШ № 13', 'school_13', 'bundled'),
    SchoolSpec('school_14', 'Россия', 'Калининградская область', 'Калининград', 'general_schools', 'Общеобразовательные школы', 'СОШ № 14', 'school_14', 'bundled'),
    SchoolSpec('school_15', 'Россия', 'Калининградская область', 'Калининград', 'general_schools', 'Общеобразовательные школы', 'СОШ № 15', 'school_15', 'bundled'),
    SchoolSpec('school_16', 'Россия', 'Калининградская область', 'Калининград', 'general_schools', 'Общеобразовательные школы', 'СОШ № 16', 'school_16', 'bundled'),
    SchoolSpec('school_19', 'Россия', 'Калининградская область', 'Калининград', 'general_schools', 'Общеобразовательные школы', 'СОШ № 19', 'school_19', 'bundled'),
    SchoolSpec('school_21', 'Россия', 'Калининградская область', 'Калининград', 'general_schools', 'Общеобразовательные школы', 'СОШ № 21', 'school_21', 'bundled'),
    SchoolSpec('school_24', 'Россия', 'Калининградская область', 'Калининград', 'general_schools', 'Общеобразовательные школы', 'СОШ № 24', 'school_24', 'bundled'),
    SchoolSpec('school_25', 'Россия', 'Калининградская область', 'Калининград', 'general_schools', 'Общеобразовательные школы', 'СОШ № 25', 'school_25', 'bundled'),
    SchoolSpec('school_26', 'Россия', 'Калининградская область', 'Калининград', 'general_schools', 'Общеобразовательные школы', 'СОШ № 26', 'school_26', 'bundled'),
    SchoolSpec('school_28', 'Россия', 'Калининградская область', 'Калининград', 'general_schools', 'Общеобразовательные школы', 'СОШ № 28', 'school_28', 'bundled'),
    SchoolSpec('school_29', 'Россия', 'Калининградская область', 'Калининград', 'general_schools', 'Общеобразовательные школы', 'СОШ № 29', 'school_29', 'bundled'),
    SchoolSpec('school_31', 'Россия', 'Калининградская область', 'Калининград', 'general_schools', 'Общеобразовательные школы', 'СОШ № 31', 'school_31', 'bundled'),
    SchoolSpec('school_33', 'Россия', 'Калининградская область', 'Калининград', 'general_schools', 'Общеобразовательные школы', 'СОШ № 33', 'school_33', 'bundled'),
    SchoolSpec('school_36', 'Россия', 'Калининградская область', 'Калининград', 'general_schools', 'Общеобразовательные школы', 'СОШ № 36', 'school_36', 'bundled'),
    SchoolSpec('school_38', 'Россия', 'Калининградская область', 'Калининград', 'general_schools', 'Общеобразовательные школы', 'СОШ № 38', 'school_38', 'bundled'),
    SchoolSpec('school_39', 'Россия', 'Калининградская область', 'Калининград', 'general_schools', 'Общеобразовательные школы', 'СОШ № 39', 'school_39', 'bundled'),
    SchoolSpec('school_41', 'Россия', 'Калининградская область', 'Калининград', 'general_schools', 'Общеобразовательные школы', 'СОШ № 41', 'school_41', 'bundled'),
    SchoolSpec('school_43', 'Россия', 'Калининградская область', 'Калининград', 'general_schools', 'Общеобразовательные школы', 'СОШ № 43', 'school_43', 'bundled'),
    SchoolSpec('school_44', 'Россия', 'Калининградская область', 'Калининград', 'general_schools', 'Общеобразовательные школы', 'СОШ № 44', 'school_44', 'bundled'),
    SchoolSpec('school_46', 'Россия', 'Калининградская область', 'Калининград', 'general_schools', 'Общеобразовательные школы', 'СОШ № 46', 'school_46', 'bundled'),
    SchoolSpec('school_47', 'Россия', 'Калининградская область', 'Калининград', 'general_schools', 'Общеобразовательные школы', 'СОШ № 47', 'school_47', 'bundled'),
    SchoolSpec('school_48', 'Россия', 'Калининградская область', 'Калининград', 'general_schools', 'Общеобразовательные школы', 'СОШ № 48', 'school_48', 'bundled'),
    SchoolSpec('school_50', 'Россия', 'Калининградская область', 'Калининград', 'general_schools', 'Общеобразовательные школы', 'СОШ № 50', 'school_50', 'bundled'),
    SchoolSpec('school_53', 'Россия', 'Калининградская область', 'Калининград', 'general_schools', 'Общеобразовательные школы', 'СОШ № 53', 'school_53', 'bundled'),
    SchoolSpec('school_56', 'Россия', 'Калининградская область', 'Калининград', 'general_schools', 'Общеобразовательные школы', 'СОШ № 56', 'school_56', 'bundled'),
    SchoolSpec('school_57', 'Россия', 'Калининградская область', 'Калининград', 'general_schools', 'Общеобразовательные школы', 'СОШ № 57', 'school_57', 'bundled'),
    SchoolSpec('school_58', 'Россия', 'Калининградская область', 'Калининград', 'general_schools', 'Общеобразовательные школы', 'СОШ № 58', 'school_58', 'bundled'),
]

TYPE_TO_CATEGORY = {
    "general": "general_schools",
    "college": "colleges",
    "university": "universities",
    "private": "private_schools",
    "boarding": "boarding_schools",
}


def asset_paths(school) -> dict[str, str]:
    base = f"/assets/{school.category}/{school.folder}"
    image_source = getattr(school, "image_source", "bundled")
    if image_source == "upload":
        path = f"/assets/uploads/schools/{school.id}/photo.webp"
        return {"desktop": path, "mobile": path}
    if image_source != "bundled":
        path = "/assets/branding/icons/school-placeholder.svg"
        return {"desktop": path, "mobile": path}
    return {"desktop": f"{base}/desktop.webp", "mobile": f"{base}/mobile.webp"}
