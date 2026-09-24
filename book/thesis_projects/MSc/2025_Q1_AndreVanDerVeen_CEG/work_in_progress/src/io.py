import os

import requests


def download_dahiti_water_level(
    dahiti_ids, api_key: str, file_format: str = "netcdf", download_folder: str = "downloads"
):
    """Download water level data from DAHITI for one or multiple IDs.

    Parameters
    ----------
    dahiti_ids : int or list[int]
        Single DAHITI ID or list of IDs
    api_key : str
        Your DAHITI API key
    file_format : str
        'netcdf', 'ascii', 'json', 'csv'
    download_folder : str
        Folder to save downloaded files (default: 'downloads')

    Returns:
    -------
    dict
        Mapping of dahiti_id -> downloaded file path (netcdf) or data (ascii/json/csv)
    """
    if isinstance(dahiti_ids, int):
        dahiti_ids = [dahiti_ids]

    os.makedirs(download_folder, exist_ok=True)
    url = "https://dahiti.dgfi.tum.de/api/v2/download-water-level/"

    results = {}
    for did in dahiti_ids:
        params = {"api_key": api_key, "dahiti_id": did, "format": file_format}
        response = requests.get(url, params=params)

        if response.status_code != 200:
            print(f"Warning: Request failed for ID {did} [{response.status_code}]")
            results[did] = None
            continue

        if file_format == "ascii":
            results[did] = response.text
        elif file_format == "json":
            results[did] = response.json()
        elif file_format == "csv":
            results[did] = response.text
        elif file_format == "netcdf":
            file_path = os.path.join(download_folder, f"{did}_water_level.nc")
            with open(file_path, "wb") as f:
                for chunk in response.iter_content(chunk_size=1024):
                    if chunk:
                        f.write(chunk)
            results[did] = file_path
        else:
            raise ValueError(f"Unknown format: {file_format}")

    return results
