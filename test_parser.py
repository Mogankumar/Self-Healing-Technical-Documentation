from doc_checker.parser import CodeParser, MarkdownParser

code_chunks = CodeParser().parse_directory(".")
doc_sections = MarkdownParser().parse_directory(".")

print(f"Found {len(code_chunks)} code chunks")
print(f"Found {len(doc_sections)} doc sections")

# Spot check
for chunk in code_chunks[:3]:
    print(f"\n[CODE] {chunk.id}")
    print(f"  signature: {chunk.signature}")
    print(f"  docstring: {chunk.docstring[:60] if chunk.docstring else 'None'}")

for section in doc_sections[:3]:
    print(f"\n[DOC] {section.id}")
    print(f"  heading_path: {section.heading_path}")