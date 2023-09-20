#!/usr/bin/env python3

import sys
import os
import argparse
import requests
import urllib3
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import concurrent.futures
import re

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)  # Disable SSL warnings

visited_urls = set()

def is_textual_content(content_type):
    return content_type.startswith('text/') or content_type == 'application/javascript'

def extract_urls(url, depth, verbose=False):
    global visited_urls
    if url in visited_urls or depth > args.depth:
        return []

    try:
        response = requests.get(url, verify=False, timeout=10)  # Disable SSL verification and set timeout
        if response.status_code != 200:
            return []
    except requests.exceptions.RequestException as e:
        if verbose:
            print(f"Error: Unable to retrieve {url} - {e}")
        return []

    visited_urls.add(url)

    content_type = response.headers.get('content-type', '')
    if not is_textual_content(content_type):
        return []

    response_content = response.content.decode('utf-8')

    soup = BeautifulSoup(response_content, 'lxml')

    extracted_urls = []

    for tag in soup.find_all(['a', 'script', 'link']):
        if tag.has_attr('href'):
            new_url = urljoin(url, tag['href'])
            extracted_urls.append(new_url)

    js_files = soup.find_all('script', attrs={'src': re.compile(r'\.js$')})
    css_files = soup.find_all('link', attrs={'rel': 'stylesheet', 'href': re.compile(r'\.css$')})

    for js_file in js_files:
        js_url = urljoin(url, js_file['src'])
        extracted_urls.append(js_url)

    for css_file in css_files:
        css_url = urljoin(url, css_file['href'])
        extracted_urls.append(css_url)

    embedded_resources = re.findall(r'(url\(["\'](.*?)["\']\))', response.text)
    for _, embedded_url in embedded_resources:
        new_url = urljoin(url, embedded_url)
        extracted_urls.append(new_url)

    third_party_scripts = soup.find_all('script', attrs={'src': re.compile(r'https?://')})
    for script in third_party_scripts:
        if 'src' in script.attrs:
            third_party_url = script['src']
            extracted_urls.append(third_party_url)

    # Extract URLs using the additional regex pattern
    links_ = re.findall('''(?#First, match the protocol)
        (?:https?|ftp|smtp)://
        (?#Next, check for optional username and/or password)
        (?#Note: The following two char classes are functionally equivalent)
        (?:[\x21-\x39\x3b-\x3f\x41-\x7e]+(?::[!-9;-?A-~]+)?@)?
        (?#Next, let's match the domain [with support for Punycode ])
        (?:xn--[0-9a-z]+|[0-9A-Za-z_-]+\.)*(?:xn--[0-9a-z]+|[0-9A-Za-z-]+)\.(?:xn--[0-9a-z]+|[0-9A-Za-z]{2,10})
        (?#Let's match on optional port)
        (?::(?:6553[0-5]|655[0-2]\d|65[0-4]\d{2}|6[0-4]\d{3}|[1-5]\d{4}|[1-9]\d{1,3}|\d))?
        (?#Next, let's match on the path)
        (?:/[\x21\x22\x24\x25\x27-x2e\x30-\x3b\x3e\x40-\x5b\x5d-\x7e]*)*
        (?#Next, let's match on an anchor)
        (?:\#[\x21\x22\x24\x25\x27-x2e\x30-\x3b\x3e\x40-\x5b\x5d-\x7e]*)?
        (?#Last, but not least, we match on URI params)
        (?:\?[\x21\x22\x24\x25\x27-\x2e\x30-\x3b\x40-\x5b\x5d-\x7e]+=[\x21\x22\x24\x25\x27-\x2e\x30-\x3b\x40-\x5b\x5d-\x7e]*)?
        (?#Additional params)
        (?:&[\x21\x22\x24\x25\x27-\x2e\x30-\x3b\x40-\x5b\x5d-\x7e]+=[\x21\x22\x24\x25\x27-\x2e\x30-\x3b\x40-\x5b\x5d-\x7e]*)*
        ''', response.text)
    extracted_urls.extend(links_)

    return extracted_urls

def save_to_file(urls, output_file):
    with open(output_file, 'a') as f:
        for url in urls:
            f.write(url + '\n')

def filter_keywords(urls_file, keywords_file, output_file):
    with open(urls_file, 'r') as f:
        urls = f.readlines()

    with open(keywords_file, 'r') as f:
        keywords = [keyword.strip() for keyword in f.readlines()]

    matching_lines = [url for url in urls if any(keyword in url for keyword in keywords)]

    with open(output_file, 'w') as f:
        f.writelines(matching_lines)

def create_output_structure(output_directory, domain_name):
    domain_directory = os.path.join(output_directory, domain_name)
    if not os.path.exists(domain_directory):
        os.makedirs(domain_directory)
    return domain_directory

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Web Crawler and URL Extractor")
    parser.add_argument("url", help="Starting URL for crawling")
    parser.add_argument("-o", "--output", default="Output", help="Output directory for extracted URLs")
    parser.add_argument("-k", "--keywords", help="File containing keywords for filtering URLs")
    parser.add_argument("-i", "--delete-input", action="store_true", help="Delete input file after creating filtered file")
    parser.add_argument("-t", "--threads", type=int, default=4, help="Number of threads or processes to use")
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable verbose mode")
    parser.add_argument("-d", "--depth", type=int, default=2, help="Depth of URL extraction")
    args = parser.parse_args()

    urls_to_extract = [(args.url, 0)]

    domain_name = args.url.split('//')[-1].split('/')[0]
    output_directory = args.output

    domain_directory = create_output_structure(output_directory, domain_name)

    output_file = os.path.join(domain_directory, f'{domain_name}.txt')

    # Create the output file (if not exists)
    open(output_file, 'a').close()

    executor_class = concurrent.futures.ThreadPoolExecutor if args.threads > 1 else concurrent.futures.ProcessPoolExecutor
    with executor_class(max_workers=args.threads) as executor:
        while urls_to_extract:
            url, depth = urls_to_extract.pop(0)
            if args.verbose:
                print(f"Processing {url}")
            futures = [executor.submit(extract_urls, u, depth + 1, args.verbose) for u in [url]]
            new_urls = []

            for future in concurrent.futures.as_completed(futures):
                new_urls.extend(future.result())

            for new_url in new_urls:
                if (
                    new_url not in visited_urls
                    and depth + 1 <= args.depth
                ):
                    save_to_file([new_url], output_file)
                    urls_to_extract.append((new_url, depth + 1))

    if args.keywords:
        filtered_output_file = os.path.join(domain_directory, f'{domain_name}_filtered.txt')
        filter_keywords(output_file, args.keywords, filtered_output_file)

        if args.delete_input and os.path.exists(output_file):
            os.remove(output_file)
