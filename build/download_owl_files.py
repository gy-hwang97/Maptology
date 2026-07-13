"""
BioPortal OWL 파일 다운로드 스크립트 / BioPortal OWL File Download Script

이 스크립트는 Maptology 앱의 빌드 과정에서 사용됩니다.
BioPortal에서 OWL/OBO 형식 온톨로지를 다운로드하고,
ontology_cache 디렉토리에 저장하며, TSV 목록 파일을 생성합니다.

- OWL 형식 → 네이티브 OWL 파일 다운로드
- OBO 형식 → BioPortal이 변환한 RDF/XML 파일 다운로드 (표시됨)
- SKOS, UMLS 등 기타 형식 → 제외

This script is used during the Maptology app build process.

사용법 / Usage:
    python download_owl_files.py
"""

import os
import sys
import csv
import time
import requests


# BioPortal API 기본 URL / BioPortal API base URL
BIOPORTAL_API_URL = "https://data.bioontology.org"

# Resolved against the repo root (this script lives in build/) rather than the
# current working directory, so the script works no matter where it is run from.
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 캐시 디렉토리 / Cache directory
CACHE_DIR = os.path.join(_REPO_ROOT, "ontology_cache")

# TSV 파일 경로 / TSV file path
TSV_FILE = os.path.join(_REPO_ROOT, "ontology_cache", "ontology_list.tsv")


def get_api_key():
    """
    사용자로부터 API 키를 입력받음 / Get API key from user input
    """
    print("=" * 60)
    print("BioPortal OWL File Download Script")
    print("=" * 60)
    print()
    print("이 스크립트는 BioPortal에서 OWL/OBO 형식 온톨로지를")
    print("다운로드합니다. (SKOS, UMLS 등은 제외)")
    print()
    print("- OWL 형식: 네이티브 OWL 파일 다운로드")
    print("- OBO 형식: RDF/XML로 변환하여 다운로드")
    print()
    print("BioPortal API 키가 필요합니다.")
    print("https://bioportal.bioontology.org/accounts 에서 발급받을 수 있습니다.")
    print()

    api_key = input("BioPortal API Key를 입력하세요: ").strip()

    if not api_key:
        print("오류: API 키가 입력되지 않았습니다. / Error: No API key provided.")
        sys.exit(1)

    return api_key


def get_all_ontologies(api_key):
    """
    BioPortal에서 모든 온톨로지 목록을 가져옴 / Fetch all ontologies from BioPortal
    """
    print("\n[1/4] 온톨로지 목록을 가져오는 중... / Fetching ontology list...")

    url = f"{BIOPORTAL_API_URL}/ontologies"
    headers = {"Authorization": f"apikey token={api_key}"}

    try:
        response = requests.get(url, headers=headers, timeout=60)
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        print(f"오류: 온톨로지 목록을 가져올 수 없습니다. / Error: Could not fetch ontology list.")
        print(f"상세: {e}")
        sys.exit(1)

    ontologies = response.json()
    print(f"  총 {len(ontologies)}개의 온톨로지를 발견했습니다. / Found {len(ontologies)} ontologies.")

    return ontologies


def filter_ontologies(ontologies, api_key):
    """
    OWL/OBO 형식 온톨로지만 필터링 / Filter OWL and OBO format ontologies
    SKOS, UMLS 등은 제외 / Exclude SKOS, UMLS, etc.
    """
    print("\n[2/4] 온톨로지 형식을 확인하는 중... / Checking ontology formats...")

    filtered_ontologies = []
    skipped_formats = {}
    total = len(ontologies)
    headers = {"Authorization": f"apikey token={api_key}"}

    for i, ont in enumerate(ontologies):
        acronym = ont.get("acronym", "")
        name = ont.get("name", "")

        # 진행 상황 표시 / Show progress
        if (i + 1) % 50 == 0 or (i + 1) == total:
            print(f"  확인 중... {i + 1}/{total}")

        # latest_submission에서 온톨로지 언어 확인 / Check ontology language
        url = f"{BIOPORTAL_API_URL}/ontologies/{acronym}/latest_submission"
        params = {"include": "hasOntologyLanguage"}

        try:
            response = requests.get(url, headers=headers, params=params, timeout=30)

            if response.status_code != 200:
                continue

            submission = response.json()
            language = str(submission.get("hasOntologyLanguage", "")).upper()

            # OWL 형식 → 네이티브 OWL로 다운로드 / OWL format → download native OWL
            if "OWL" in language:
                filtered_ontologies.append({
                    "acronym": acronym,
                    "name": name,
                    "native_format": "OWL",
                    "download_format": "OWL"
                })

            # OBO 형식 → RDF/XML로 변환하여 다운로드 / OBO format → download as RDF/XML
            elif "OBO" in language:
                filtered_ontologies.append({
                    "acronym": acronym,
                    "name": name,
                    "native_format": "OBO",
                    "download_format": "RDF/XML"
                })

            # 기타 형식은 제외 / Skip other formats
            else:
                fmt = language if language else "UNKNOWN"
                skipped_formats[fmt] = skipped_formats.get(fmt, 0) + 1

        except requests.exceptions.RequestException:
            continue

        # API 요청 속도 제한 방지 / Avoid API rate limiting
        time.sleep(0.1)

    # 결과 요약 / Summary
    owl_count = sum(1 for o in filtered_ontologies if o["download_format"] == "OWL")
    rdf_count = sum(1 for o in filtered_ontologies if o["download_format"] == "RDF/XML")

    print(f"\n  결과 요약 / Summary:")
    print(f"    OWL 형식 (네이티브 다운로드): {owl_count}개")
    print(f"    OBO 형식 (RDF/XML 변환 다운로드): {rdf_count}개")
    print(f"    총 다운로드 대상: {len(filtered_ontologies)}개")

    if skipped_formats:
        print(f"    제외된 형식 / Skipped formats:")
        for fmt, count in skipped_formats.items():
            print(f"      {fmt}: {count}개")

    return filtered_ontologies


def download_files(filtered_ontologies, api_key):
    """
    온톨로지 파일을 다운로드하고 캐시에 저장 / Download ontology files and save to cache
    - OWL 형식: 네이티브 OWL 파일 / OWL format: native OWL file
    - OBO 형식: RDF/XML로 변환 / OBO format: converted to RDF/XML
    """
    print(f"\n[3/4] 파일을 다운로드하는 중... / Downloading files...")

    # 캐시 디렉토리 생성 / Create cache directory
    os.makedirs(CACHE_DIR, exist_ok=True)

    headers = {"Authorization": f"apikey token={api_key}"}
    downloaded = []
    failed = []
    total = len(filtered_ontologies)

    for i, ont in enumerate(filtered_ontologies):
        acronym = ont["acronym"]
        name = ont["name"]
        download_format = ont["download_format"]
        native_format = ont["native_format"]
        file_path = os.path.join(CACHE_DIR, f"{acronym}.owl")

        format_label = f"[{download_format}]"
        print(f"  [{i + 1}/{total}] {acronym} {format_label} 다운로드 중...", end="", flush=True)

        # 이미 다운로드된 파일이 있으면 건너뜀 / Skip if already downloaded
        if os.path.exists(file_path) and os.path.getsize(file_path) > 0:
            print(" 이미 존재 (건너뜀) / Already exists (skipped)")
            downloaded.append({
                "name": name,
                "file_path": file_path,
                "acronym": acronym,
                "native_format": native_format,
                "download_format": download_format
            })
            continue

        # 다운로드 URL 설정 / Set download URL
        url = f"{BIOPORTAL_API_URL}/ontologies/{acronym}/download"

        # OWL → 네이티브 다운로드 (파라미터 없음)
        # OBO → RDF/XML로 변환 다운로드 (download_format=rdf)
        if native_format == "OWL":
            params = {}
        else:
            params = {"download_format": "rdf"}

        try:
            response = requests.get(
                url,
                headers=headers,
                params=params,
                timeout=300,
                stream=True
            )

            if response.status_code == 200:
                # 스트리밍으로 파일 저장 / Save file with streaming
                with open(file_path, "wb") as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        f.write(chunk)

                file_size_mb = os.path.getsize(file_path) / (1024 * 1024)
                print(f" 완료 ({file_size_mb:.1f} MB)")

                downloaded.append({
                    "name": name,
                    "file_path": file_path,
                    "acronym": acronym,
                    "native_format": native_format,
                    "download_format": download_format
                })
            else:
                print(f" 실패 (HTTP {response.status_code})")
                failed.append(acronym)

        except requests.exceptions.RequestException as e:
            print(f" 실패: {e}")
            failed.append(acronym)

        # API 요청 속도 제한 방지 / Avoid API rate limiting
        time.sleep(0.5)

    # 결과 요약 / Summary
    owl_downloaded = sum(1 for d in downloaded if d["download_format"] == "OWL")
    rdf_downloaded = sum(1 for d in downloaded if d["download_format"] == "RDF/XML")

    print(f"\n  다운로드 완료 / Download complete:")
    print(f"    OWL 파일: {owl_downloaded}개")
    print(f"    RDF/XML 파일 (OBO 변환): {rdf_downloaded}개")
    print(f"    총 다운로드: {len(downloaded)}개")

    if failed:
        print(f"    실패: {len(failed)}개 — {', '.join(failed)}")

    return downloaded


def create_tsv_file(downloaded):
    """
    온톨로지 목록 TSV 파일 생성 / Create ontology list TSV file
    format 컬럼에 OWL 또는 RDF/XML 표시 / Show OWL or RDF/XML in format column
    """
    print(f"\n[4/4] TSV 파일을 생성하는 중... / Creating TSV file...")

    with open(TSV_FILE, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f, delimiter="\t")

        # 헤더 작성 / Write header
        writer.writerow(["name", "file_path", "abbreviation", "native_format", "download_format"])

        # 데이터 작성 / Write data
        for ont in downloaded:
            writer.writerow([
                ont["name"],
                ont["file_path"],
                ont["acronym"],
                ont["native_format"],
                ont["download_format"]
            ])

    # 요약 / Summary
    owl_count = sum(1 for d in downloaded if d["download_format"] == "OWL")
    rdf_count = sum(1 for d in downloaded if d["download_format"] == "RDF/XML")

    print(f"  TSV 파일 저장 완료: {TSV_FILE}")
    print(f"  총 {len(downloaded)}개 기록 (OWL: {owl_count}개, RDF/XML: {rdf_count}개)")


def main():
    """
    메인 함수 / Main function
    """
    # 1. API 키 입력 / Get API key
    api_key = get_api_key()

    # 2. 전체 온톨로지 목록 가져오기 / Get all ontologies
    ontologies = get_all_ontologies(api_key)

    # 3. OWL/OBO 형식만 필터링 / Filter OWL and OBO ontologies
    filtered_ontologies = filter_ontologies(ontologies, api_key)

    # 4. 파일 다운로드 / Download files
    downloaded = download_files(filtered_ontologies, api_key)

    # 5. TSV 파일 생성 / Create TSV file
    create_tsv_file(downloaded)

    # 완료 메시지 / Done
    print("\n" + "=" * 60)
    print("완료! / Done!")
    print(f"  캐시 디렉토리 / Cache directory: {CACHE_DIR}/")
    print(f"  온톨로지 목록 / Ontology list: {TSV_FILE}")
    print("=" * 60)


if __name__ == "__main__":
    main()