# mojofmt

Formatter for Mojolicious Embedded Perl templates (.ep, .htm.ep, .html.ep)

mojofmt formats HTML and Mojolicious EP templates without breaking embedded Perl. It understands line directives (% ...), inline tags (<% ... %>), raw HTML blocks, and can reformat multi-line Perl blocks inside <% ... %> using perltidy (with a safe fallback if perltidy isn’t available).

## Features

- Indents HTML structure and Mojolicious line directives consistently
- Preserves chomp markers (<%- ... -%>) and does not alter newline semantics
- Formats inline EP tags:
  - <%= ... %> expressions (keeps them single-line)
  - <% ... %> one-line statements
- Re-formats extended multi-line Perl blocks between lines with only <% and %> (or chomped variants), using perltidy or a naive brace-aware indenter
- Treats pre/script/style/textarea content as opaque (unchanged)
- Optional spacing normalization inside <% %> delimiters
- Optional aggressive spacing after common Perl keywords (--perl-keyword-spacing)
- End-of-line normalization (lf, crlf, or preserve)
- CLI with --write, --check, --diff, --out, --stdin/--stdout
- Self-test mode to sanity-check behavior and perltidy availability

## Requirements

- Python 3.8+ (3.11+ recommended)
- Optional but recommended: perltidy (Perl::Tidy)
  - Debian/Ubuntu: apt-get install perltidy
  - CPAN: cpanm Perl::Tidy
  - mojofmt will fall back to a simple brace-based indenter for extended blocks if perltidy is absent or fails

## Install

- Clone this repository
- Make the script executable and put it on your PATH, or run it in place

```
chmod +x mojofmt.py
./mojofmt.py --version
```

## Usage

Basic formatting to stdout:
- ./mojofmt.py path/to/template.html.ep
- cat file.ep | ./mojofmt.py --stdin --stdout

Write changes in place (creates a .bak backup):
- ./mojofmt.py -w templates/

Check mode (exit 1 if any file would change):
- ./mojofmt.py --check templates/

Show a diff:
- ./mojofmt.py --diff path/to/file.ep

Write output to a separate file:
- ./mojofmt.py -o formatted.ep path/to/file.ep
- cat file.ep | ./mojofmt.py --stdin -o formatted.ep

Control indentation (spaces per level):
- ./mojofmt.py --indent 4 file.ep

Normalize EOLs:
- ./mojofmt.py --eol lf file.ep
- ./mojofmt.py --eol crlf file.ep
- ./mojofmt.py --eol preserve file.ep

Perl spacing knobs:
- Add spacing after common Perl keywords: ./mojofmt.py --perl-keyword-spacing file.ep
- Pass a specific perltidy binary: ./mojofmt.py --perltidy /usr/bin/perltidy file.ep
- See perltidy status: ./mojofmt.py --self-test

Increase logging:
- ./mojofmt.py --log-level debug file.ep
- ./mojofmt.py --verbose file.ep  (shorthand for info)

## How it works

- HTML indentation:
  - Tracks opening/closing tags; avoids indenting void/self-closing tags
  - pre/script/style/textarea bodies are untouched
- Mojolicious directives:
  - Lines starting with % are indented relative to HTML and Perl block depth
  - begin/end and { ... } braces adjust indentation depth
- Inline EP tags on a line:
  - <%= ... %> expressions are normalized via perltidy in an expression-safe wrapper
  - <% ... %> one-line statements are normalized via perltidy (or left as-is if perltidy is missing)
  - Optional normalization of spaces inside <% %> delimiters can be disabled with --no-space-in-delims
- Extended multi-line Perl blocks:
  - Detected when <% (or <%-) is on a line by itself, and %> (or -%>) is on a line by itself
  - The inner Perl is dedented, wrapped in do { ... } and run through perltidy; if that fails or perltidy is missing, a brace-aware fallback indenter is used
  - Inner lines are re-indented to match the opening/closing delimiter’s indentation
- EOL normalization:
  - Input CRLF/CR are normalized internally; output can be forced to lf/crlf or preserve the original

## Examples

Before:
```
<ul>
% for my $i (1..3) {
<li><%= $i%></li>
%}
</ul>
```

After:
```
<ul>
    % for my $i (1 .. 3) {
        <li><%= $i %></li>
    % }
</ul>
```

Extended Perl block:
```
<%
my $x=1;
if($x){
say"hi";
}
%>
```

Becomes (with --indent 4):
```
<%
my $x = 1;
if ($x) {
    say "hi";
}
%>
```

## Options

- -w, --write: Overwrite files in place (writes a .bak backup)
- -o, --out FILE: Write formatted output to FILE (single input or --stdin)
- --check: Exit non-zero if any file would change
- --diff: Print unified diff
- --stdin / --stdout: Pipe mode
- --perltidy PATH: Path to perltidy executable
- --indent N: Indent width (spaces; default 2)
- --eol lf|crlf|preserve: End-of-line handling (default lf)
- --no-space-in-delims: Do not normalize spacing inside <% %> delimiters
- --perl-keyword-spacing: Aggressively insert a space after common Perl keywords
- --self-test: Run internal sanity checks and perltidy probe
- --log-level error|info|debug: Logging verbosity (or use --verbose)
- --version: Print version

## File selection

By default, mojofmt processes:
- .ep
- .htm.ep
- .html.ep

Directories are walked recursively; only matching files are formatted.

## Tips and caveats

- perltidy recommended: For best results on complex Perl inside templates, install perltidy. mojofmt falls back to a brace-aware indenter for extended blocks, but won’t do token-level Perl formatting without perltidy.
- Extended block detection: Only triggers when the opening <% (or <%-) and closing %> (or -%>) are on their own lines. Inline <% ... %> on the same line are handled by the inline path.
- Raw blocks: Content inside pre/script/style/textarea is not changed.
- Chomp markers: Left/right chomps (<%- and -%>) are preserved and not moved.
- Idempotent: Running mojofmt repeatedly should not keep changing the file (self-test checks this).
- EOLs: Use --eol preserve to retain original line endings.

## Troubleshooting

- perltidy non-zero exit N in debug logs:
  - mojofmt wraps extended blocks in do { ... } for perltidy; if it still fails, run perltidy manually on the wrapper to see the error.
  - Ensure perltidy is on PATH or pass --perltidy /path/to/perltidy.
- Extended block didn’t reformat:
  - Confirm the delimiters are on their own lines (no code on the <% / %> lines).
  - Run with --log-level debug to see whether perltidy or the naive indenter handled the block.
- Spaces around Perl keywords:
  - Off by default. Enable with --perl-keyword-spacing if you want if(...)->if (...), my$->my $, return(...)->return (...), etc.

## Development

Run self-tests:
- ./mojofmt.py --self-test
- Use --log-level debug for detailed logs

Format from stdin to stdout:
- python3 mojofmt.py --stdin --stdout < in.ep > out.ep

Generate a diff without writing:
- python3 mojofmt.py --diff path/to/file.html.ep

## Contributing

- Open an issue or pull request with a clear description and a minimal repro template
- Please include before/after snippets and your command-line flags
- If you modify formatting rules, add/adjust a self-test where possible

## License

See LICENSE file in this repository. If you don’t have one yet, consider MIT or Apache-2.0.

## Acknowledgments

- Mojolicious and Mojo::Template for the EP syntax
- Perl::Tidy for robust Perl formatting