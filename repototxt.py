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

load_dotenv()

try:
    GITHUB_TOKEN = os.environ["GITHUB_TOKEN"]
except KeyError:
    GITHUB_TOKEN = None
    print("Warning: GitHub Personal Access Token not found in environment variables.")
    print("You will only be able to convert local repositories")

OUTPUT_DIR = os.getenv("OUTPUT_DIR", "")
ENABLE_CLIPBOARD = (
    bool(os.getenv("ENABLE_CLIPBOARD")) and os.getenv("ENABLE_CLIPBOARD") != "0"
)
ENABLE_SAVE_TO_FILE = (
    bool(os.getenv("ENABLE_SAVE_TO_FILE", "1"))
    and os.getenv("ENABLE_SAVE_TO_FILE") != "0"
)

TIMESTAMP = bool(os.getenv("TIMESTAMP")) and os.getenv("TIMESTAMP") != "0"

app = typer.Typer()
console = Console()


def is_github_repo_url(input_path: str) -> bool:
    return input_path.startswith("https://github.com/")


def extract_repo_path(repo_url: str) -> str:
    if "github.com" not in repo_url:
        return ""
    parts = repo_url.split("github.com/")
    return parts[1] if len(parts) == 2 else ""


def copy_to_clipboard(text: str):
    pyperclip.copy(text)
    console.print("[green]Text copied to clipboard![/green]")


def save_to_file(text: str, filename: str, output_dir: Path):
    output_filename = f"{filename}.txt"
    if TIMESTAMP:
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


def get_local_readme_content(directory_path):
    """
    Retrieve the content of the README file in a local directory.
    """
    readme_path = os.path.join(directory_path, "README.md")
    if os.path.exists(readme_path):
        try:
            with open(readme_path, "r", encoding="utf-8") as readme_file:
                return readme_file.read()
        except Exception as e:
            return f"Error reading README file: {e}"
    else:
        return "README not found."


def get_structure_iteratively(repo):
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
            if content.type == "dir":
                if content.path not in dirs_visited:
                    structure += f"{path}/{content.name}/\n"
                    dirs_to_visit.append(
                        (f"{path}/{content.name}", repo.get_contents(content.path))
                    )
            else:
                structure += f"{path}/{content.name}\n"
    return structure


def get_local_structure(directory_path):
    """
    Generate the structure of a local directory, excluding the .git folder.
    """
    structure = ""
    for root, dirs, files in os.walk(directory_path):
        dirs[:] = [d for d in dirs if d != ".git"]  # Exclude the .git folder
        for dir_name in dirs:
            dir_path = os.path.join(root, dir_name)
            relative_path = os.path.relpath(dir_path, directory_path)
            structure += f"{relative_path}/\n"

        for file_name in files:
            file_path = os.path.join(root, file_name)
            relative_path = os.path.relpath(file_path, directory_path)
            structure += f"{relative_path}\n"
    return structure


def get_file_contents_iteratively(repo):
    file_contents = ""
    dirs_to_visit = [("", repo.get_contents(""))]
    dirs_visited = set()
    global BINARY_EXTENSIONS

    while dirs_to_visit:
        path, contents = dirs_to_visit.pop()
        dirs_visited.add(path)
        for content in tqdm(contents, desc=f"Downloading {path}", leave=False):
            if content.type == "dir":
                if content.path not in dirs_visited:
                    dirs_to_visit.append(
                        (f"{path}/{content.name}", repo.get_contents(content.path))
                    )
            else:
                # Skip the README file
                if content.name.lower() == "readme.md":
                    continue

                # Check if the file extension suggests it's a binary file
                if any(content.name.endswith(ext) for ext in BINARY_EXTENSIONS):
                    file_contents += (
                        f"File: {path}/{content.name}\nContent: Skipped binary file\n\n"
                    )
                else:
                    file_contents += f"File: {path}/{content.name}\n"
                    try:
                        if content.encoding is None or content.encoding == "none":
                            file_contents += (
                                "Content: Skipped due to missing encoding\n\n"
                            )
                        else:
                            try:
                                decoded_content = content.decoded_content.decode(
                                    "utf-8"
                                )
                                file_contents += f"Content:\n{decoded_content}\n\n"
                            except UnicodeDecodeError:
                                try:
                                    decoded_content = content.decoded_content.decode(
                                        "latin-1"
                                    )
                                    file_contents += f"Content (Latin-1 Decoded):\n{decoded_content}\n\n"
                                except UnicodeDecodeError:
                                    file_contents += "Content: Skipped due to unsupported encoding\n\n"
                    except (AttributeError, UnicodeDecodeError):
                        file_contents += "Content: Skipped due to decoding error or missing decoded_content\n\n"
    return file_contents


def get_local_file_contents_iteratively(directory_path):
    """
    Generate the contents of files in a local directory, excluding the .git folder and README file.
    """
    file_contents = ""
    global BINARY_EXTENSIONS

    for root, dirs, files in os.walk(directory_path):
        dirs[:] = [d for d in dirs if d != ".git"]  # Exclude the .git folder
        for file_name in files:
            file_path = os.path.join(root, file_name)
            relative_path = os.path.relpath(file_path, directory_path)

            # Skip the README file and files in the .git folder
            if relative_path.startswith(".git/") or file_name.lower() == "readme.md":
                continue

            file_contents += f"File: {relative_path}\n"
            if any(file_name.endswith(ext) for ext in BINARY_EXTENSIONS):
                file_contents += "Content: Skipped binary file\n\n"
            else:
                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        content = f.read()
                    file_contents += f"Content:\n{content}\n\n"
                except UnicodeDecodeError:
                    try:
                        with open(file_path, "r", encoding="latin-1") as f:
                            content = f.read()
                        file_contents += f"Content (Latin-1 Decoded):\n{content}\n\n"
                    except UnicodeDecodeError:
                        file_contents += (
                            "Content: Skipped due to unsupported encoding\n\n"
                        )
                except Exception as e:
                    file_contents += f"Content: Skipped due to error: {str(e)}\n\n"
    return file_contents


def get_instructions(prompt_path, repo_name):
    with open(prompt_path, "r", encoding="utf-8") as f:
        instructions = f.read()
        instructions = instructions.replace("##REPO_NAME##", repo_name)
        return instructions


def set_functions(is_local):
    if is_local:
        get_readme = get_local_readme_content
        get_structure = get_local_structure
        get_files = get_local_file_contents_iteratively
    else:
        get_readme = get_readme_content
        get_structure = get_structure_iteratively
        get_files = get_file_contents_iteratively

    return get_readme, get_structure, get_files


def get_text(
    repo_path_or_url,
    is_local=False,
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
        Path.cwd(), help="Directory to save the text output"
    ),
):
    if not (ENABLE_CLIPBOARD or ENABLE_SAVE_TO_FILE):
        console.print(
            "[red]ERROR: CLIPBOARD and SAVE TO FILE disabled, enable one and try again![/red]"
        )
        raise typer.Exit(code=1)

    output = ""
    if is_github_repo_url(input_path):
        set_functions(False)
        # output = analyze_github_repo(input_path, github_token)
        repo_name, output = get_text(input_path)
    elif os.path.isdir(input_path):
        repo_name, output = get_text(input_path, True)
    else:
        console.print(
            "[red]Invalid input. Please provide a valid local directory path or a full GitHub repository URL.[/red]"
        )
        raise typer.Exit(code=1)

    if ENABLE_CLIPBOARD:
        copy_to_clipboard(output)

    if ENABLE_SAVE_TO_FILE:
        save_to_file(output, repo_name, output_dir)


if __name__ == "__main__":
    app()
