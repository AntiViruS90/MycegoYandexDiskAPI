import os
import zipfile
import urllib.parse
from io import BytesIO
import requests
from django.shortcuts import render, redirect
from django.http import HttpResponse
from django.conf import settings
from typing import List
from django.core.cache import cache
import aiohttp

YANDEX_DISK_API_URL = "https://cloud-api.yandex.net/v1/disk/public/resources"


def get_files_from_public_link(public_key: str, media_type: str = None) -> List[dict]:
    """
    Retrieve a list of files and folders from a public Yandex.Disk link.

    This function fetches files and folders from a Yandex.Disk public link, with optional filtering
    by media type. It uses caching to improve performance for repeated requests.

    Args:
        public_key (str): The public key or link to the Yandex.Disk folder.
        media_type (str, optional): The media type to filter the results. If None, all types are returned.

    Returns:
        List[dict]: A list of dictionaries, where each dictionary represents a file or folder
        with its metadata. The list is empty if no items are found or if an error occurs.

    Note:
        This function uses pagination to fetch all items, with a limit of 50 items per request.
        Results are cached for 1 hour to reduce API calls for repeated requests.
    """
    cache_key = f"files_{public_key}_{media_type}"
    cached_files = cache.get(cache_key)

    if cached_files is not None:
        return cached_files

    url = f"{YANDEX_DISK_API_URL}?public_key={public_key}"
    headers = {
        "Authorization": f"OAuth {settings.YANDEX_DISK_TOKEN}"
    }
    files = []
    offset = 0
    limit = 50

    while True:
        params = {
            "limit": limit,
            "offset": offset
        }

        response = requests.get(url, headers=headers, params=params)

        if response.status_code == 200:
            data = response.json()

            # Получаем данные из _embedded
            embedded = data.get('_embedded', {})
            items = embedded.get('items', [])

            if not items:
                break

            for item in items:
                if media_type and item.get('media_type') != media_type:
                    continue
                files.append(item)

            offset += limit
        else:
            print(f"Ошибка {response.status_code}: {response.text}")
            break

    cache.set(cache_key, files, timeout=3600)
    return files


def get_download_link(public_key: str, file_path: str) -> str:
    """
    Get a download link for a file from Yandex.Disk.

    This function constructs and sends a request to the Yandex.Disk API to retrieve
    a download link for a specific file within a public folder.

    Args:
        public_key (str): The public key of the Yandex.Disk folder. This is typically
                          the last part of the public folder's URL.
        file_path (str): The path to the file within the public folder.

    Returns:
        str: A direct download link for the specified file if successful,
             or an empty string if the request fails.

    Note:
        This function modifies the input parameters before making the API request.
        It appends part of the file_path to the public_key and truncates the file_path.
    """
    public_key = public_key + '//' + file_path[:31]
    file_path = file_path[31:]

    encoded_file_path = urllib.parse.quote_plus(file_path)
    print(f"encoded_file_path: {encoded_file_path}")
    url = f"{YANDEX_DISK_API_URL}/download?public_key={public_key}&path={encoded_file_path}"
    print(f"URL: {url}")
    headers = {
        "Authorization": f"OAuth {settings.YANDEX_DISK_TOKEN}"
    }
    response = requests.get(url, headers=headers)

    if response.status_code == 200:
        return response.json().get('href', '')
    else:
        return ''


async def get_download_link_async(public_key: str, file_path: str) -> str:
    """
    Asynchronously retrieve a download link for a file from Yandex.Disk.

    This function constructs a URL to request a download link for a specific file
    within a public Yandex.Disk folder and sends an asynchronous GET request to
    the Yandex.Disk API.

    Args:
        public_key (str): The public key of the Yandex.Disk folder. This is typically
                          the last part of the public folder's URL.
        file_path (str): The path to the file within the public folder.

    Returns:
        str: A direct download link for the specified file if the request is successful,
             or an empty string if the request fails or the link is not found in the response.

    Note:
        This function requires the aiohttp library for asynchronous HTTP requests
        and assumes that YANDEX_DISK_API_URL and settings.YANDEX_DISK_TOKEN are
        defined elsewhere in the code.
    """
    download_url = f"{YANDEX_DISK_API_URL}/download?public_key={public_key}&path={file_path}"
    print(f"Link async download_url: {download_url}")

    async with aiohttp.ClientSession() as session:
        async with session.get(download_url,
                               headers={"Authorization": f"OAuth {settings.YANDEX_DISK_TOKEN}"}) as response:
            if response.status == 200:
                data = await response.json()
                return data.get('href', '')
            else:
                return ''


def index(request):
    """
    Главная страница для ввода публичной ссылки на папку и фильтрации файлов.

    Processes HTTP GET and POST requests. If the request is POST, retrieves the public key and
    optional media_type parameter from the POST request data. Then calls the function
    get_files_from_public_link to get a list of files and folders from a specified folder
    on Yandex.Disk. The results are displayed in the 'files/file_list.html' template.
    If the request is GET, the template 'files/index.html' is displayed.

    Parameters:
    request (HttpRequest): Incoming HTTP request.

    Returns:
    HttpResponse: HTTP response containing the template 'files/file_list.html' with data about files and folders,
                  if the request is POST. Or an HTTP response containing the template 'files/index.html',
                  if the request is GET.
    """
    if request.method == "POST":
        public_key = request.POST["public_key"]
        media_type = request.POST.get("media_type", None)
        files = get_files_from_public_link(public_key, media_type)
        return render(request, 'files/file_list.html',
                      {'files': files, 'public_key': public_key, 'media_type': media_type})

    return render(request, 'files/index.html')


def download_file(request, public_key, file_path):
    """
    Download a selected file from Yandex.Disk.

    This function handles the HTTP request to download a specific file from a Yandex.Disk
    public folder. It checks if the file path starts with a forward slash and removes it if necessary.
    Then, it retrieves a download link for the file using the `get_download_link` function.
    If a download link is available, it redirects the user to the download link.
    Otherwise, it returns an HTTP response with an error message and a status code of 400.

    Parameters:
    request (HttpRequest): The incoming HTTP request.
    public_key (str): The public key of the Yandex.Disk folder containing the file.
    file_path (str): The path to the file within the public folder.

    Returns:
    HttpResponse: An HTTP response redirecting to the download link if successful,
                 or an HTTP response with an error message and a status code of 400 if
                 the download link is not available.
    """
    if file_path.startswith('/'):
        file_path = file_path[1:]

    download_url = get_download_link(public_key, file_path)
    if download_url:
        return redirect(download_url)
    return HttpResponse("Ошибка при получении ссылки для скачивания.", status=400)


async def create_zip_archive_from_yandex(public_key, file_paths):
    """
    Asynchronously create a ZIP archive with files downloaded from Yandex.Disk.

    This function takes a public key for a Yandex.Disk folder and a list of file paths,
    downloads the specified files from Yandex.Disk, and creates a ZIP archive containing
    these files in memory.

    Args:
        public_key (str): The public key of the Yandex.Disk folder containing the files.
        file_paths (list): A list of file paths (strings) to be included in the ZIP archive.

    Returns:
        BytesIO: A BytesIO object containing the ZIP archive data. The buffer is
                 positioned at the beginning of the data (seek(0) has been called).

    Raises:
        Any exceptions raised by aiohttp.ClientSession or zipfile operations are not
        caught in this function and will propagate to the caller.

    Note:
        This function uses asynchronous I/O operations to improve performance when
        dealing with multiple files. It relies on the get_download_link_async function
        to obtain download URLs for each file.
    """
    print(f"zip_archive from yandex public_key: {public_key}")
    print(f"zip_archive from yandex file_paths: {file_paths}")

    zip_buffer = BytesIO()  # Буфер для хранения архива в памяти

    # Открываем архив в память
    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
        # Для каждого файла в списке
        for file_path in file_paths:
            # Вызов асинхронной функции для получения ссылки для скачивания
            download_url = await get_download_link_async(public_key, file_path)
            print(f"ZipFile download url: {download_url}")

            if download_url:
                # Загружаем файл с Яндекс.Диска
                async with aiohttp.ClientSession() as session:
                    async with session.get(download_url) as response:
                        if response.status == 200:
                            # Добавляем файл в архив. Имя файла будет таким же, как и у исходного.
                            zip_file.writestr(file_path, await response.read())
                        else:
                            print(f"Ошибка при загрузке файла: {file_path}")
            else:
                print(f"Не удалось получить ссылку на файл: {file_path}")

    # После того как архив собран, возвращаемся к началу буфера
    zip_buffer.seek(0)
    return zip_buffer


async def download_multiple_files(request, public_key):
    """
    Download multiple files from Yandex.Disk into a ZIP archive.

    This function handles HTTP POST requests to download multiple files from a Yandex.Disk
    public folder into a ZIP archive. It retrieves the list of files to download from the
    request POST data, creates a ZIP archive using the `create_zip_archive_from_yandex`
    function, and returns the ZIP archive as an HTTP response.

    Args:
        request (HttpRequest): The incoming HTTP request.
        public_key (str): The public key of the Yandex.Disk folder containing the files.

    Returns:
        HttpResponse: An HTTP response containing the ZIP archive of the selected files.
                      If the request method is not POST, it returns a response with a status
                      code of 405 (Method Not Allowed). If no files are selected for download,
                      it returns a response with a status code of 400 (Bad Request).

    Note:
        This function requires the aiohttp library for asynchronous HTTP requests.
    """
    if request.method == "POST":
        files_to_download = request.POST.getlist('files')
        print(f"Files to download: {files_to_download}")

        if not files_to_download:
            return HttpResponse("Ошибка: Не выбраны файлы для скачивания.", status=400)

        # Create a ZIP archive with the selected files from Yandex.Disk
        zip_buffer = await create_zip_archive_from_yandex(public_key, files_to_download)

        # Return the ZIP archive as an HTTP response
        response = HttpResponse(zip_buffer.getvalue(), content_type='application/zip')
        response['Content-Disposition'] = 'attachment; filename="files.zip"'
        return response

    return HttpResponse("Метод не поддерживается.", status=405)


def create_zip_archive(file_paths: List[str]) -> BytesIO:
    """
     Create a ZIP archive with multiple files.

    The function takes a list of file paths and creates a ZIP archive,
    containing the specified files. Files are added to the archive with the same names
    same as the source files.

    Parameters:
    file_paths (List[str]): List of file paths to be added to the archive.
                           Each path must be relative to the MEDIA_ROOT folder.

    Returns:
    BytesIO: An in-memory buffer containing the created ZIP archive.
             The buffer position is set to the beginning (called seek(0)).
    """
    zip_buffer = BytesIO()  # Буфер для хранения архива в памяти

    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
        for file_path in file_paths:
            print(f"file_path in create_zip_archive: {file_path}")
            # Абсолютный путь до файла на сервере (замените на путь к вашим файлам на диске)
            file_full_path = os.path.join(settings.MEDIA_ROOT, file_path.lstrip('/'))

            # Проверяем, существует ли файл
            if os.path.exists(file_full_path):
                # Имя файла в архиве будет таким же, как и у исходного
                zip_file.write(file_full_path, os.path.basename(file_path))

    zip_buffer.seek(0)  # Возвращаемся к началу буфера
    return zip_buffer
