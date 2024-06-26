#!/usr/bin/env python3
import os
from github import Github
from pathlib import Path
import pyperclip
import typer
from rich.console import Console
from dotenv import load_dotenv
import datetime
from tqdm import tqdm
from bin_ext import BINARY_EXTENSIONS
import json
from typing import Optional
import fnmatch

load_dotenv()

try:
    GITHUB_TOKEN = os.environ["GITHUB_TOKEN"]
except KeyError:
    GITHUB_TOKEN = None
    print("Warning: GitHub Personal Access Token not found in environment variables.")
    print("You will only be able to convert local repositories")

BINARY_EXTENSIONS = set(BINARY_EXTENSIONS)  # Convert to set for efficient lookup
# -------------------------------------------------------------------------------------------------
app = typer.Typer()
console = Console()


def read_config(config_path: str = "config.json") -> dict:
    """
    Reads configuration from a JSON file and returns the configuration as a dictionary.
    """
    try:
        with open(config_path, "r") as f:
            config = json.load(f)
    except FileNotFoundError:
        config = {}
    except json.JSONDecodeError:
        raise Exception("Error decoding JSON configuration file.")
    return config


CONFIG = read_config()


def get_config_value(key: str, default: Optional[bool] = None) -> Optional[bool]:
    """
    Helper function to fetch a configuration value given its key,
    with an optional default if the key doesn't exist.
    """
    return CONFIG.get(key, default)


def is_github_repo_url(input_path: str) -> bool:
    return input_path.startswith("https://github.com/")


def extract_repo_path(repo_url: str) -> str:
    if "github.com" not in repo_url:
        return ""
    parts = repo_url.split("github.com/")
    return parts[1] if len(parts) == 2 else ""


def parse_ignore_patterns(directory_path: str) -> list:
    """
    Parses both .gitignore and .gptignore files in the provided directory,
    returns a list of patterns to ignore. Patterns in .gptignore take precedence.
    """
    ignore_files = [".gitignore", ".gptignore"]
    ignore_patterns = []

    for ignore_file in ignore_files:
        try:
            with open(os.path.join(directory_path, ignore_file), "r") as f:
                for line in f:
                    cleaned_line = line.strip()
                    if cleaned_line and not cleaned_line.startswith("#"):
                        ignore_patterns.append(cleaned_line)
        except FileNotFoundError:
            pass  # Ignore the error if the file does not exist

    if not ignore_patterns:
        ignore_patterns.extend([".git", ".gitignore", "**/.env"])

    return list(set(ignore_patterns))  # remove duplicates


def copy_to_clipboard(text: str):
    pyperclip.copy(text)
    console.print("[green]Text copied to clipboard![/green]")


def save_to_file(text: str, filename: str, output_dir: Path, timestamp_option: bool):
    output_filename = f"{filename}.txt"
    if timestamp_option:
        output_filename = f"{filename}_{get_timestamp()}.txt"
    output_file_path = output_dir.joinpath(output_filename)
    with open(output_file_path, "w") as file:
        file.write(text)
    console.print(f"[green]Text saved to file: {output_file_path}[/green]")


def get_timestamp():
    now = datetime.datetime.now()
    timestamp = now.strftime("%Y-%m-%d_%H-%M-%S")
    return timestamp


def get_readme_content(repo):
    """
    Retrieve the content of the README file.
    """
    try:
        readme = repo.get_contents("README.md")
        return readme.decoded_content.decode("utf-8")
    except:
        return "README not found."


def get_local_readme_content(path):
    """
    Retrieve the content of the README file in a local directory.
    Improved error handling and consistency in parameter naming.
    """
    readme_path = os.path.join(path, "README.md")
    if os.path.exists(readme_path):
        try:
            with open(readme_path, "r", encoding="utf-8") as readme_file:
                return readme_file.read()
        except Exception as e:
            return f"Error reading README file: {e}"
    else:
        return "README not found."


def get_repo_structure(repo):
    """
    Traverse the repository iteratively to avoid recursion limits for large repositories.
    """
    structure = ""
    dirs_to_visit = [("", repo.get_contents(""))]
    dirs_visited = set()

    while dirs_to_visit:
        path, contents = dirs_to_visit.pop()
        dirs_visited.add(path)
        for content in tqdm(contents, desc=f"Processing {path}", leave=False):
            if content.type == "dir" and content.path not in dirs_visited:
                structure += f"{path}/{content.name}/\n"
                dirs_to_visit.append(
                    (f"{path}/{content.name}", repo.get_contents(content.path))
                )
            else:
                structure += f"{path}/{content.name}\n"
    return structure


def get_local_repo_structure(path):
    """
    Generate the structure of a local directory, excluding the .git folder, README file and accounting for .gptignore.
    """
    ignore_patterns = parse_ignore_patterns(path)
    print(ignore_patterns)
    structure = ""
    for root, dirs, files in os.walk(path):
        dirs[:] = [
            d
            for d in dirs
            if d != ".git"
            and not any(fnmatch.fnmatch(d, pattern) for pattern in ignore_patterns)
        ]
        files = [
            f
            for f in files
            if not any(
                fnmatch.fnmatch(os.path.join(root, f), pattern)
                for pattern in ignore_patterns
            )
        ]

        for dir_name in dirs:
            relative_path = os.path.relpath(os.path.join(root, dir_name), path)
            structure += f"{relative_path}/\n"

        for file_name in files:
            relative_path = os.path.relpath(os.path.join(root, file_name), path)
            structure += f"{relative_path}\n"
    return structure


def get_file_contents(repo):
    file_contents_list = []  # Use a list to improve string building efficiency
    dirs_to_visit = [("", repo.get_contents(""))]
    dirs_visited = set()

    while dirs_to_visit:
        path, contents = dirs_to_visit.pop()
        dirs_visited.add(path)
        for content in tqdm(contents, desc=f"Downloading {path}", leave=False):
            if content.type == "dir" and content.path not in dirs_visited:
                dirs_to_visit.append(
                    (f"{path}/{content.name}", repo.get_contents(content.path))
                )
            else:
                # Skip README files
                if content.name.lower() == "readme.md":
                    continue

                content_descriptor = f"File: {path}/{content.name}\n"
                if any(
                    content.name.endswith(ext) for ext in BINARY_EXTENSIONS
                ):  # Efficient lookup
                    file_contents_list.append(
                        content_descriptor + "Content: Skipped binary file\n\n"
                    )
                else:
                    # Only construct the content string if needed
                    content_string = "Content: "
                    try:
                        decoded_content = content.decoded_content.decode("utf-8")
                        content_string += f"\n{decoded_content}\n\n"
                    except UnicodeDecodeError:
                        content_string += "Skipped due to unsupported encoding\n\n"
                    except AttributeError:
                        content_string += "Skipped due to decoding error or missing decoded_content\n\n"

                    file_contents_list.append(content_descriptor + content_string)
    return "".join(file_contents_list)  # Join the list into a single string at the end


def get_local_file_contents(path):
    """
    Generate the contents of files in a local directory, excluding the .git folder, README file and  also accounting for .gptignore.
    """
    ignore_patterns = parse_ignore_patterns(path)
    file_contents_list = []

    for root, dirs, files in os.walk(path):
        dirs[:] = [
            d
            for d in dirs
            if d != ".git"
            and not any(fnmatch.fnmatch(d, pattern) for pattern in ignore_patterns)
        ]
        files = [
            f
            for f in files
            if not any(fnmatch.fnmatch(f, pattern) for pattern in ignore_patterns)
            and f.lower() != "readme.md"
        ]

        for file_name in files:
            if file_name.lower() == "readme.md":
                continue
            file_path = os.path.join(root, file_name)
            relative_path = os.path.relpath(file_path, path)

            content_descriptor = f"File: {relative_path}\n"
            file_extension = os.path.splitext(file_name)[1]
            if file_extension in BINARY_EXTENSIONS:
                file_contents_list.append(
                    content_descriptor + "Content: Skipped binary file\n\n"
                )
            else:
                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        content = f.read()
                    file_contents_list.append(
                        content_descriptor + f"Content:\n{content}\n\n"
                    )
                except UnicodeDecodeError:
                    try:
                        with open(file_path, "r", encoding="latin-1") as f:
                            content = f.read()
                        file_contents_list.append(
                            content_descriptor
                            + f"Content (Latin-1 Decoded):\n{content}\n\n"
                        )
                    except UnicodeDecodeError:
                        file_contents_list.append(
                            content_descriptor
                            + "Content: Skipped due to unsupported encoding\n\n"
                        )
                except Exception as e:
                    file_contents_list.append(
                        content_descriptor
                        + f"Content: Skipped due to error: {str(e)}\n\n"
                    )

    return "".join(file_contents_list)


def get_instructions(prompt_path, repo_name):
    with open(prompt_path, "r", encoding="utf-8") as f:
        instructions = f.read()
        instructions = instructions.replace("##REPO_NAME##", repo_name)
        return instructions


def set_functions(is_local):
    if is_local:
        get_readme = get_local_readme_content
        get_structure = get_local_repo_structure
        get_files = get_local_file_contents
    else:
        get_readme = get_readme_content
        get_structure = get_repo_structure
        get_files = get_file_contents

    return get_readme, get_structure, get_files


def get_text(
    repo_path_or_url,
    is_local=False,
    no_prompt=False,
):
    """
    Main function to get repository contents.
    """

    (
        get_readme,
        get_structure,
        get_files,
    ) = set_functions(is_local)
    repo_name = repo_path_or_url.split("/")[-1]
    if is_local:
        repo_or_path = repo_path_or_url
    else:
        if not GITHUB_TOKEN:
            raise ValueError(
                "Please set the 'GITHUB_TOKEN' environment variable or the 'GITHUB_TOKEN' in the script."
            )
        g = Github(GITHUB_TOKEN)
        repo_or_path = g.get_repo(repo_path_or_url.replace("https://github.com/", ""))

    print(f"Fetching README for: {repo_name}")
    readme_content = get_readme(repo_or_path)

    print(f"\nFetching repository structure for: {repo_name}")
    repo_structure = f"Repository Structure: {repo_name}\n"
    repo_structure += get_structure(repo_or_path)

    print(f"\nFetching file contents for: {repo_name}")
    file_contents = get_files(repo_or_path)

    instructions = ""
    if not no_prompt:
        instructions = get_instructions("instructions-prompt.txt", repo_name)

    text = f"{instructions}\n\nREADME:\n{readme_content}\n\n{repo_structure}\n\n{file_contents}"

    return repo_name, text


@app.command()
def analyze(
    input_path: str = typer.Argument(
        ..., help="Path to the local directory or full GitHub repository URL"
    ),
    github_token: str = typer.Option(
        None,
        envvar=["GITHUB_TOKEN"],
        help="GitHub Personal Access Token for GitHub repository analysis.",
    ),
    output_dir: Path = typer.Option(
        Path(get_config_value("output_directory", "./")),
        help="Directory to save the text output",
    ),
    save_to_file_option: bool = typer.Option(
        get_config_value("save_to_file", True),
        "--save",
        "-s",
        help="Toggle whether to save the analysis result to a file",
    ),
    copy_to_clipboard_option: bool = typer.Option(
        get_config_value("copy_to_clipboard", True),
        "--copy",
        "-c",
        help="Toggle whether to copy the analysis result to the clipboard",
    ),
    timestamp_option: bool = typer.Option(
        get_config_value("timestamp_option", True),
        "--time",
        "-t",
        help="Toggle whether to save file with timestamp",
    ),
    no_prompt: bool = typer.Option(
        False,
        "--no-prompt",
        "-np",
        help="Toggle whether to exclude the instructions prompt from the output",
    ),
):
    if not (copy_to_clipboard_option or save_to_file_option):
        console.print(
            "[red]ERROR: CLIPBOARD and SAVE TO FILE disabled, enable one and try again![/red]"
        )
        raise typer.Exit(code=1)

    output = ""
    if is_github_repo_url(input_path):
        set_functions(False)
        repo_name, output = get_text(input_path, no_prompt=no_prompt)
    elif os.path.isdir(input_path):
        repo_name, output = get_text(input_path, True, no_prompt=no_prompt)
    else:
        console.print(
            "[red]Invalid input. Please provide a valid local directory path or a full GitHub repository URL.[/red]"
        )
        raise typer.Exit(code=1)

    if copy_to_clipboard_option:
        copy_to_clipboard(output)

    if save_to_file_option:
        save_to_file(output, repo_name, output_dir, timestamp_option)


if __name__ == "__main__":
    app()
