"""
Insurance PDF Parser

A Python application that monitors a directory for PDF files from Czech insurance companies
(Allianz, Kooperativa, Generali) and extracts insurance policy data into a CSV database.

Author: Jiri Eifler
Date: 2025
"""

import os
import re
import time
from typing import Dict, Any

import fitz  # PyMuPDF
import pandas as pd
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

# Configuration constants
from PDF_Parser.config import WATCH_FOLDER, CSV_PATH, SORTED_FOLDER, ERROR_FOLDER


def extract_common_fields() -> Dict[str, str]:
    """
    Define the common data structure for all insurance companies.

    Returns:
        Dict[str, str]: Dictionary with all possible fields initialized as empty strings
    """
    return {
        "Jméno a příjmení": "",
        "Rodné číslo": "",
        "Datum narození": "",
        "Adresa": "",
        "Číslo smlouvy": "",
        "SPZ": "",
        "Cena vozidla": "",
        "Najeté km": "",
        "Roční nájezd": "",
        "Počátek pojištění": "",
        "Cena": "",
        "Krytí PR": "",
        "Havarijní pojištění": "",
        "Další připojištění": "",
        "Telefon": "",
        "E-mail": "",
        "Pojistník - Typ osoby": "",
        "Pojistník - Plátce DPH": "",
        "Shodný provozovatel": "",
        "Shodný vlastník": "",
        "Provozovatel - Název": "",
        "Provozovatel - IČO": "",
        "Provozovatel - Adresa": "",
        "Provozovatel - Typ osoby": "",
        "Provozovatel - Plátce DPH": "",
        "Vlastník - Název": "",
        "Vlastník - IČO": "",
        "Vlastník - Adresa": "",
        "Vlastník - Typ osoby": "",
        "Vlastník - Plátce DPH": "",
        "Zdrojový soubor": ""
    }


COLUMNS = list(extract_common_fields().keys())


def clean_phone_number(phone_raw: str) -> str:
    """
    Clean and format Czech phone number to 9-digit format.

    Args:
        phone_raw (str): Raw phone number string from document

    Returns:
        str: Cleaned 9-digit phone number or empty string if invalid
    """
    if not phone_raw:
        return ""

    # Remove all non-digit characters
    phone_clean = re.sub(r"\D", "", phone_raw)

    # Remove Czech country code prefixes
    if phone_clean.startswith("420"):
        phone_clean = phone_clean[3:]
    elif phone_clean.startswith("00420"):
        phone_clean = phone_clean[5:]

    return phone_clean if len(phone_clean) == 9 else ""


def parse_birth_number(birth_number: str) -> str:
    """
    Parse Czech birth number (rodné číslo) to birth date.

    Args:
        birth_number (str): Czech birth number (9-10 digits)

    Returns:
        str: Birth date in DD.MM.YYYY format or empty string if invalid
    """
    if not birth_number or not re.match(r"\d{6}", birth_number):
        return ""

    rc = birth_number.replace("/", "")
    year = int(rc[:2])
    year += 1900 if year >= 50 else 2000

    return f"{rc[4:6]}.{rc[2:4]}.{year}"


# ====================== ALLIANZ EXTRACTOR ======================

def extract_data_allianz(text: str, filename: str) -> Dict[str, Any]:
    """
    Extract insurance data from Allianz PDF documents.

    Args:
        text (str): Extracted text from PDF document
        filename (str): Source PDF filename

    Returns:
        Dict[str, Any]: Dictionary containing extracted insurance data
    """
    lines = text.splitlines()
    text_lower = text.lower()
    data = extract_common_fields()
    data["Zdrojový soubor"] = filename

    def search_pattern(pattern: str, group: int = 1) -> str:
        """Search for regex pattern in text and return specified group."""
        match = re.search(pattern, text)
        return match.group(group).strip() if match else ""

    def search_after_line(startswith: str, offset: int = 1) -> str:
        """Find line starting with text and return line at offset."""
        for i, line in enumerate(lines):
            if startswith.lower() in line.lower():
                if i + offset < len(lines):
                    return lines[i + offset].strip()
        return ""

    # Extract name and surname
    for i, line in enumerate(lines):
        if "Rodné číslo" in line and i > 0:
            previous_line = lines[i - 1].strip()
            if previous_line:
                data["Jméno a příjmení"] = previous_line.split("\n")[0].strip()
            break

    # Fallback for name extraction
    if not data["Jméno a příjmení"]:
        jmeno_line = search_after_line("Klient (Vy):")
        if jmeno_line:
            data["Jméno a příjmení"] = jmeno_line.strip().split("\n")[0]

    # Extract birth number and parse birth date
    data["Rodné číslo"] = search_pattern(r"Rodné číslo:\s*(\d{9,10})")
    data["Datum narození"] = parse_birth_number(data["Rodné číslo"])

    # Extract address
    for i, line in enumerate(lines):
        if "trvalý pobyt" in line.lower():
            for j in range(i + 1, i + 3):
                if j < len(lines) and lines[j].strip():
                    data["Adresa"] = lines[j].strip()
                    break
            break

    # Extract license plate
    spz_match = re.search(r"([A-Z0-9]{5,8}), č\.", text)
    if spz_match:
        data["SPZ"] = spz_match.group(1)

    # Extract contract number
    data["Číslo smlouvy"] = search_pattern(r"Nabídka pojistitele č\.\s*(\d+)")

    # Extract insurance start date
    data["Počátek pojištění"] = search_pattern(r"KČ ROČNĚ\s+(\d{1,2}\.\s*\d{1,2}\.\s*\d{4})")

    # Extract annual mileage
    data["Roční nájezd"] = search_pattern(r"Roční nájezd:\s*(Do\s*[\d\s]+km)")

    # Extract and clean phone number
    telefon_raw = search_pattern(r"Mobilní telefon:\s*([\+0-9 ]+)")
    data["Telefon"] = clean_phone_number(telefon_raw)

    # Extract email address
    email_found = ""
    for i, line in enumerate(lines):
        if "kontaktní adresa" in line.lower():
            for j in range(i + 1, min(i + 6, len(lines))):
                email_match = re.search(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+", lines[j])
                if email_match:
                    email_found = email_match.group(0).strip()
                    break
            break

    if not email_found:
        email_match = re.search(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+", text)
        email_found = email_match.group(0).strip() if email_match else ""

    data["E-mail"] = email_found

    # Extract liability coverage limits
    kryti_match = re.search(r"Limit.*?(\d{2,3})\s*/\s*(\d{2,3})", text, re.IGNORECASE)
    if kryti_match:
        data["Krytí PR"] = f"{kryti_match.group(1)}/{kryti_match.group(2)}"

    # Check if operator and owner are the same as policyholder
    data["Shodný provozovatel"] = "ANO" if "provozovatel je shodný" in text_lower else "NE"
    data["Shodný vlastník"] = "ANO" if "vlastník vozidla je shodný" in text_lower else "NE"

    # Extract additional insurance packages
    cleaned_text = re.sub(r"\s+", " ", text_lower)

    balicky_pravidla = {
        "Sjednaný balíček Max": ["havárie ano", "doplatek na nové (gap) ano", "gap ano"],
        "Sjednaný balíček Extra": ["krádež ano", "skla ano", "vandalismus ano"],
        "Sjednaný balíček Plus": ["přírodní události ano", "požár a výbuch ano", "poškození zvířetem ano"],
        "Sjednaný balíček Komfort": ["povinné ručení ano", "právní poradenství ano", "asistence ano",
                                     "rozšířená asistence ano", "úrazové pojištění ano"]
    }

    for nazev_balicku, keywords in balicky_pravidla.items():
        for keyword in keywords:
            if keyword in cleaned_text:
                data["Další připojištění"] = nazev_balicku
                break
        if data["Další připojištění"]:
            break

    # Check for comprehensive insurance
    havarijni = ["přírodní události", "poškození zvířetem", "havárie", "gap", "skla", "krádež"]
    data["Havarijní pojištění"] = "ANO" if any(f"{kw} ano" in text_lower for kw in havarijni) else "NE"

    # Extract vehicle price
    cena_vozidla_match = re.search(r"Cena vozidla\s*[:\-]?\s*([\d\s]+)\s*Kč", text, re.IGNORECASE)
    data["Cena vozidla"] = cena_vozidla_match.group(1).replace(" ", "") if cena_vozidla_match else "neuvedeno"

    # Extract mileage
    najezd_match = re.search(r"Najeté km\s*[:\-]?\s*([\d\s]+)", text, re.IGNORECASE)
    data["Najeté km"] = najezd_match.group(1).replace(" ", "") if najezd_match else "neuvedeno"

    # Extract total price
    data["Cena"] = "neuvedeno"
    for i, line in enumerate(lines):
        if "vaše pojistné" in line.lower():
            for j in range(1, 4):
                if i + j < len(lines):
                    match = re.search(r"([0-9]{1,3}(?:[ \u00A0]?[0-9]{3}))\s*Kč", lines[i + j])
                    if match:
                        data["Cena"] = match.group(1).replace(" ", "").replace("\u00A0", "")
                        break
            break

    return data


# ====================== KOOPERATIVA EXTRACTOR ======================

def extract_data_koop(text: str, filename: str) -> Dict[str, Any]:
    """
    Extract insurance data from Kooperativa PDF documents.

    Args:
        text (str): Extracted text from PDF document
        filename (str): Source PDF filename

    Returns:
        Dict[str, Any]: Dictionary containing extracted insurance data
    """
    data = extract_common_fields()
    data["Zdrojový soubor"] = filename

    def find_pattern(pattern: str, group: int = 1, default: str = "") -> str:
        """Find regex pattern in text with error handling."""
        match = re.search(pattern, text)
        try:
            return match.group(group).strip()
        except:
            return default

    def find_block(label: str, group: int = 1) -> str:
        """Find labeled block in text."""
        return find_pattern(rf"{label}\s+([^\n]*)", group)

    # Extract basic information
    data["Jméno a příjmení"] = find_block(r"Titul, jméno, příjmení")
    data["Rodné číslo"] = find_pattern(r"Rodné číslo\s+(\d{9,10})")
    data["Datum narození"] = parse_birth_number(data["Rodné číslo"])
    data["Adresa"] = find_block(r"Adresa bydliště")
    data["Číslo smlouvy"] = find_pattern(r"\b(\d{10})\b")
    data["SPZ"] = find_block(r"Registrační značka")

    # Extract financial information
    data["Cena vozidla"] = find_pattern(r"Pojistná částka\s+([\d\s]+)", 1).replace(" ", "")
    data["Najeté km"] = find_pattern(r"Stav počítadla \(km\)\s+([\d\s]+)", 1).replace(" ", "")
    data["Počátek pojištění"] = find_pattern(r"Počátek pojištění\s+(\d{1,2}\.\s*\d{1,2}\.\s*\d{4})")
    data["Cena"] = find_pattern(r"Celkové roční pojistné\s+([\d\s]+)", 1).replace(" ", "")

    # Extract liability coverage
    limit_matches = re.findall(r"(\d{2,3})\s*mil\.\s*Kč", text)
    if len(limit_matches) >= 2:
        data["Krytí PR"] = f"{limit_matches[0]}/{limit_matches[1]}"
    else:
        data["Krytí PR"] = "neuvedeno"

    # Check operator and owner status
    data["Shodný provozovatel"] = ("ANO" if re.search(r"Provozovatel\s+Shodný\s+s\s+pojistníkem", text, re.IGNORECASE)
                                   else "NE")
    data["Shodný vlastník"] = ("ANO" if re.search(r"Vlastník\s+Shodný\s+s\s+pojistníkem", text, re.IGNORECASE)
                               else "NE")

    # Extract contact information
    telefon_raw = find_pattern(r"Mobil\s+([\+0-9 ]+)")
    data["Telefon"] = clean_phone_number(telefon_raw)

    email_match = re.search(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+", text)
    data["E-mail"] = email_match.group(0) if email_match else ""

    data["Pojistník - Typ osoby"] = find_pattern(r"Typ osoby\s+([^\n]+)")

    # Extract additional insurance
    block = re.search(r"Doplňková pojištění(.*?)(?:Roční pojistné|$)", text, re.DOTALL)
    if block:
        items = [r.strip() for r in block.group(1).split("\n") if "pojištění" in r.lower()]
        data["Další připojištění"] = ", ".join(sorted(set(items)))

    data["Havarijní pojištění"] = "ANO" if "Havarijní pojištění" in text else "NE"

    return data


# ====================== GENERALI EXTRACTOR ======================

def extract_data_generali(text: str, filename: str) -> Dict[str, Any]:
    """
    Extract insurance data from Generali PDF documents.

    Args:
        text (str): Extracted text from PDF document
        filename (str): Source PDF filename

    Returns:
        Dict[str, Any]: Dictionary containing extracted insurance data
    """
    data = extract_common_fields()
    data["Zdrojový soubor"] = filename

    # Extract policyholder information
    pojistnik_match = re.search(
        r"POJISTNÍK\s*-\s*fyzická osoba\s*(.*?)\n(?:PRACOVNÍK|POJISTNÁ|TECHNICKÉ|POJIŠTĚNÍ|$)",
        text,
        re.DOTALL | re.IGNORECASE
    )

    if pojistnik_match:
        pojistnik_text = pojistnik_match.group(1)

        def extract_field(label: str) -> str:
            """Extract field from policyholder block."""
            pattern = rf"{re.escape(label)}\s*:\s*(.+)"
            match = re.search(pattern, pojistnik_text)
            return match.group(1).strip() if match else ""

        data["Jméno a příjmení"] = extract_field("Titul, jméno, příjmení, titul za jménem")
        data["Rodné číslo"] = extract_field("Rodné číslo")
        data["Datum narození"] = parse_birth_number(data["Rodné číslo"].replace("/", ""))

        telefon_raw = extract_field("Telefon")
        data["Telefon"] = clean_phone_number(telefon_raw)

        data["E-mail"] = extract_field("E-mail")
        data["Adresa"] = extract_field("Trvalá adresa")
        data["Pojistník - Typ osoby"] = "fyzická osoba"

    # Extract contract number
    smlouva_match = re.search(r"Pojistná smlouva číslo\s*:\s*(\d+)", text)
    if smlouva_match:
        data["Číslo smlouvy"] = smlouva_match.group(1).strip()

    # Extract vehicle information
    vozidlo_match = re.search(
        r"3\.3\s+Údaje o vozidle\s*(.*?)\n(?:3\.4|POJIŠTĚNÍ|TECHNICKÉ|$)",
        text,
        re.DOTALL | re.IGNORECASE
    )

    if vozidlo_match:
        vozidlo_text = vozidlo_match.group(1)

        def extract_car_field(label: str) -> str:
            """Extract field from vehicle block."""
            pattern = rf"{re.escape(label)}\s*:\s*(.+)"
            match = re.search(pattern, vozidlo_text)
            return match.group(1).strip() if match else ""

        data["SPZ"] = extract_car_field("Registrační značka")

    # Extract insurance start date
    pocatek_match = re.search(r"počátkem pojištění\s+(\d{1,2}\.\s*\d{1,2}\.\s*\d{4})", text, re.IGNORECASE)
    if pocatek_match:
        data["Počátek pojištění"] = pocatek_match.group(1).strip()

    # Extract liability coverage
    kryti_match = re.search(
        r"Limit pojistného plnění.*?(\d{2,3})\s*[\d\s]*Kč.*?škody na majetku.*?(\d{2,3})\s*[\d\s]*Kč",
        text,
        re.DOTALL | re.IGNORECASE
    )
    if kryti_match:
        castka_zdravi = kryti_match.group(1).strip()
        castka_skoda = kryti_match.group(2).strip()
        data["Krytí PR"] = f"{castka_zdravi}/{castka_skoda}"

    # Extract premium amount
    cena_patterns = [
        r"Celkem roční pojistné.*?([0-9\s]{4,7})\s*Kč",
        r"Výše jednotlivé splátky.*?([0-9\s]{4,7})\s*Kč",
        r"Částka\s*([0-9\s]{4,7})\s*Kč"
    ]

    for pattern in cena_patterns:
        cena_match = re.search(pattern, text, re.IGNORECASE)
        if cena_match:
            data["Cena"] = cena_match.group(1).replace(" ", "")
            break

    # Extract additional insurance
    pripojisteni_match = re.search(r"4\.2\s+Doplňková pojištění\s+(.*)", text, re.IGNORECASE)
    if pripojisteni_match:
        data["Další připojištění"] = pripojisteni_match.group(1).strip()

    # Check for comprehensive insurance
    text_lower = text.lower()
    havarijni_keywords = [
        "havarijní pojištění", "poškození zvířetem", "přírodní události",
        "havárie", "skla", "krádež", "vandalismus", "gap"
    ]
    data["Havarijní pojištění"] = "ANO" if any(kw in text_lower for kw in havarijni_keywords) else "NE"

    # Extract vehicle price
    vozidlo_match = re.search(r"cena vozidla\s*[:\-]?\s*([0-9\s]{4,10})", text, re.IGNORECASE)
    data["Cena vozidla"] = (vozidlo_match.group(1).replace(" ", "") if vozidlo_match
                            else "neuvedeno")

    # Extract mileage information
    najete_km_match = re.search(r"Najeté kilometry\s*[:\-]?\s*([0-9\s]{1,10})", text, re.IGNORECASE)
    data["Najeté km"] = (najete_km_match.group(1).replace(" ", "") if najete_km_match
                         else "neuvedeno")

    rocni_najezd_match = re.search(r"Roční nájezd\s*[:\-]?\s*([0-9\s]{1,10})", text, re.IGNORECASE)
    data["Roční nájezd"] = (rocni_najezd_match.group(1).replace(" ", "") if rocni_najezd_match
                            else "neuvedeno")

    # Extract VAT payer status
    data["Pojistník - Plátce DPH"] = ("ANO" if re.search(r"Plátce DPH\s*[:\-]?\s*ano", text, re.IGNORECASE)
                                      else "neuvedeno")

    # Check operator status
    provozovatel_match = re.search(
        r"3\.2\s+Držitel\s+\(provozovatel\)\s+vozidla\s+je\s+shodný\s+s\s+pojistníkem",
        text,
        re.IGNORECASE
    )
    data["Shodný provozovatel"] = "ANO" if provozovatel_match else "NE"

    # Extract owner information
    vlastnik_match = re.search(r"3\.1\s+Vlastník vozidla:\s*(.+)", text)
    if vlastnik_match:
        data["Vlastník - Název"] = vlastnik_match.group(1).strip()
        data["Shodný vlastník"] = "NE"
    else:
        data["Vlastník - Název"] = "neuvedeno"
        data["Shodný vlastník"] = "NE"

    return data


# ====================== FILE SYSTEM HANDLER ======================

class PDFHandler(FileSystemEventHandler):
    """
    File system event handler for processing new PDF files.

    This class monitors a directory for new PDF files and automatically
    processes them to extract insurance data.
    """

    def on_created(self, event):
        """
        Handle file creation events.

        Args:
            event: File system event object containing file path information
        """
        if event.is_directory or not event.src_path.lower().endswith(".pdf"):
            return

        filename = os.path.basename(event.src_path)
        print(f"📥 New PDF file detected: {filename}")

        try:
            # Extract text from PDF
            doc = fitz.open(event.src_path)
            text = "".join([page.get_text() for page in doc])
            doc.close()

            if not text.strip():
                print("🔍 No text found, skipping file.")
                return

            # Determine insurance company and extract data
            text_lower = text.lower()
            if "allianz" in text_lower:
                data = extract_data_allianz(text, filename)
                print("🏢 Processing Allianz document")
            elif "kooperativa" in text_lower:
                data = extract_data_koop(text, filename)
                print("🏢 Processing Kooperativa document")
            elif "generali" in text_lower or "česká podnikatelská" in text_lower:
                data = extract_data_generali(text, filename)
                print("🏢 Processing Generali document")
            else:
                print("❌ Unsupported insurance company - skipping file.")
                self._move_to_error_folder(event.src_path, filename)
                return

            # Save data to CSV
            self._save_to_csv(data)
            self._move_to_processed_folder(event.src_path, filename)
            print("✅ Data extracted and file processed successfully.")

        except Exception as e:
            print(f"❌ Error processing {filename}: {e}")
            self._move_to_error_folder(event.src_path, filename)

    def _save_to_csv(self, data: Dict[str, Any]) -> None:
        """
        Save extracted data to CSV file.

        Args:
            data (Dict[str, Any]): Extracted insurance data
        """
        df_new = pd.DataFrame([[data.get(col, "") for col in COLUMNS]], columns=COLUMNS)

        if os.path.exists(CSV_PATH):
            df_old = pd.read_csv(CSV_PATH)
            df_full = pd.concat([df_old, df_new], ignore_index=True)
        else:
            df_full = df_new

        df_full.to_csv(CSV_PATH, index=False)

    def _move_to_processed_folder(self, src_path: str, filename: str) -> None:
        """
        Move successfully processed file to sorted folder.

        Args:
            src_path (str): Source file path
            filename (str): Original filename
        """
        os.rename(src_path, os.path.join(SORTED_FOLDER, filename))

    def _move_to_error_folder(self, src_path: str, filename: str) -> None:
        """
        Move problematic file to error folder.

        Args:
            src_path (str): Source file path
            filename (str): Original filename
        """
        os.rename(src_path, os.path.join(ERROR_FOLDER, filename))


def setup_directories() -> None:
    """Create necessary directories if they don't exist."""
    os.makedirs(SORTED_FOLDER, exist_ok=True)
    os.makedirs(ERROR_FOLDER, exist_ok=True)


def main() -> None:
    """
    Main function to start the PDF monitoring service.

    Sets up directory monitoring and starts the file watcher service
    that processes PDF files from Czech insurance companies.
    """
    print("👀 Monitoring folder for new PDF files (Allianz, Kooperativa, Generali)...")
    print(f"📁 Watch folder: {WATCH_FOLDER}")
    print(f"📊 CSV output: {CSV_PATH}")
    print(f"✅ Processed files: {SORTED_FOLDER}")
    print(f"❌ Error files: {ERROR_FOLDER}")
    print("-" * 60)

    setup_directories()

    event_handler = PDFHandler()
    observer = Observer()
    observer.schedule(event_handler, WATCH_FOLDER, recursive=False)
    observer.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n🛑 Stopping PDF monitor service...")
        observer.stop()

    observer.join()
    print("✅ Service stopped successfully.")


if __name__ == "__main__":
    main()