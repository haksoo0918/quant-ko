import glob
import re
import sys

if sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

md_files = glob.glob("**/*.md", recursive=True)
md_files = [
    f for f in md_files
    if not f.startswith(".venv") and not f.startswith(".git")
]

bold_pattern = re.compile(r"(?<=\S)\*\*(?=[가-힣])")
# unescaped single tilde not part of ~~strikethrough~~
tilde_pattern = re.compile(r"(?<!\\)(?<!~)~(?!~)")

total_tilde = 0
total_bold = 0

for file in sorted(md_files):
    with open(file, encoding="utf-8") as f:
        content = f.read()

    lines = content.splitlines()
    in_code_block = False

    tilde_issues = []
    bold_issues = []

    for idx, line in enumerate(lines, 1):
        if line.strip().startswith("```"):
            in_code_block = not in_code_block
            continue
        if in_code_block:
            continue

        # Ignore inline code spans `...`
        stripped_line = re.sub(r"`[^`]*`", "", line)
        # Ignore markdown strikethrough ~~...~~
        stripped_line = re.sub(r"~~.*?~~", "", stripped_line)

        t_matches = list(tilde_pattern.finditer(stripped_line))
        if t_matches:
            tilde_issues.append((idx, line.strip()))

        b_matches = list(bold_pattern.finditer(stripped_line))
        if b_matches:
            bold_issues.append((idx, line.strip()))

    if tilde_issues or bold_issues:
        print(f"=== {file} ===")
        if tilde_issues:
            print(f"  [Unescaped ~]: {len(tilde_issues)} lines")
            for lno, text in tilde_issues:
                print(f"    L{lno}: {text}")
        if bold_issues:
            print(f"  [Bold glued]: {len(bold_issues)} lines")
            for lno, text in bold_issues:
                print(f"    L{lno}: {text}")
        print()
        total_tilde += len(tilde_issues)
        total_bold += len(bold_issues)

print("--------------------------------------------------")
print(f"Total markdown files scanned: {len(md_files)}")
print(f"Total unescaped tildes: {total_tilde}")
print(f"Total bold-korean glued: {total_bold}")
