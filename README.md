# Mojolicious Template Formatter

This Python program formats Mojolicious template files to make their structure easily understandable by humans. It properly indents HTML tags, Mojolicious commands, helper commands, and Perl constructs.

## Features

- Proper indentation of HTML tags
- Formatting of Mojolicious command lines (% lines)
- Proper handling of Perl code blocks
- Special handling for Mojolicious-specific syntax (form_for, content_for, etc.)
- Ensures space after % when required
- Customizable indentation size
- Smart handling of non-indenting tags (br, hr, img, input, etc.)
- Special handling for lines with multiple closing tags

## Usage

```bash
# Basic usage
./mojo_formatter_final.py input_file.mojo > output_file.mojo

# Read from stdin and write to stdout
cat input_file.mojo | ./mojo_formatter_final.py > output_file.mojo

# Specify custom indentation size (default is 4 spaces)
./mojo_formatter_final.py --indent 8 input_file.mojo > output_file.mojo

# Show help
./mojo_formatter_final.py --help
```

## Examples

The formatter can handle various Mojolicious template constructs, including:

- HTML tags
- Mojolicious command lines (% lines)
- Perl code blocks
- Form blocks
- Content blocks
- Embedded Perl expressions
- Special HTML elements like `<br>`, `<hr>`, `<img>`, etc.

## Requirements

- Python 3.x
- No external dependencies required

## How It Works

The formatter uses regular expressions to identify different elements in the Mojolicious template:

1. Mojolicious command lines (starting with %)
2. HTML tags
3. Perl code blocks
4. Special Mojolicious constructs (form_for, content_for)

It then applies appropriate indentation based on the nesting level of these elements, with special handling for non-indenting tags and multiple closing tags.