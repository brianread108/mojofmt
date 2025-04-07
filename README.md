# Mojolicious Template Formatter

This Python program formats Mojolicious template files to make their structure easily understandable by humans. It properly indents HTML tags, Mojolicious commands, helper commands, and Perl constructs.

## Features

- **HTML Tag Indentation**: Properly indents HTML tags and nested elements
- **Mojolicious Command Formatting**: Formats Mojolicious command lines (% lines) with proper spacing
- **Perl Code Block Formatting**: Intelligently handles Perl code blocks and their nesting
- **Special Syntax Handling**: Special handling for Mojolicious-specific syntax (form_for, content_for blocks)
- **Embedded Perl Formatting**: Uses perltidy to format embedded Perl code blocks
- **Smart Tag Handling**: Special handling for self-closing tags, minimal indentation for span/p tags
- **Customizable Indentation**: Configurable indentation size (default: 4 spaces)
- **Perltidy Output Files**: Option to save original and formatted Perl code to separate files

## Installation

No installation is required. The formatter is a standalone Python script that can be run directly.

### Requirements

- Python 3.6 or higher
- perltidy (for Perl code formatting)

To install perltidy:

```bash
sudo apt-get install perltidy
```

## Usage

### Basic Usage

```bash
./mojo_formatter_final_fixed8.py input_file.mojo > output_file.mojo
```

### With Custom Indentation

```bash
./mojo_formatter_final_fixed8.py --indent 2 input_file.mojo > output_file.mojo
```

### With Perltidy Output Files

```bash
./mojo_formatter_final_fixed8.py --perltidy-output-dir=/path/to/output/dir input_file.mojo > output_file.mojo
```

### With Debug Logging

```bash
./mojo_formatter_final_fixed8.py --debug input_file.mojo > output_file.mojo
```

## How It Works

The formatter processes Mojolicious template files in several passes:

1. **Embedded Perl Processing**: Extracts and formats embedded Perl code using perltidy
2. **Line-by-Line Processing**: Processes each line based on its type (HTML or Mojolicious command)
3. **Post-Processing**: Handles special cases like multiple closing tags on a single line
4. **Duplicate Tag Cleanup**: Normalizes and removes duplicate closing tags

## Special Features

### Smart HTML Tag Handling

- Non-indenting tags like `<br>`, `<hr>`, `<img>`, etc. don't cause indentation changes
- Minimal indentation for `<span>` and `<p>` tags (half the normal indentation)
- Special handling for lines with multiple closing tags

### Embedded Perl Formatting

The formatter uses perltidy to format embedded Perl code blocks (enclosed in `<%` and `%>` tags). This ensures that your Perl code follows consistent formatting rules.

### Perltidy Output Files

When using the `--perltidy-output-dir` option, the formatter saves both the original and formatted Perl code for each embedded Perl block to separate files:

- `perl_block_N_original.pl`: The original Perl code before formatting
- `perl_block_N_formatted.pl`: The formatted Perl code after perltidy processing

## Example

### Input

```perl
<div>
<% 
# This is a test of pure Perl code with minimal indentation
if ($status) {
    $c->desktopBackupRecordStatus($backup_rec, 'pre-backup', $status);
    return ($c->l('bac_OPERATION_STATUS_REPORT').$c->l('bac_ERR_PRE_BACKUP'));
}

my $clvl = $c->stash('compressionlevel');
my $cmd = "/bin/tar --create --file=- --directory / @{$c->stash('exclude')}  "
    . "@{$c->stash('directories')} | /usr/bin/gzip $clvl ";
%>
</div>
```

### Output

```perl
<div>
    <%
    # This is a test of pure Perl code with minimal indentation
    if ($status) {
        $c->desktopBackupRecordStatus($backup_rec, 'pre-backup', $status);
        return ($c->l('bac_OPERATION_STATUS_REPORT') . $c->l('bac_ERR_PRE_BACKUP'));
    }
    my $clvl = $c->stash('compressionlevel');
    my $cmd  = "/bin/tar --create --file=- --directory / @{$c->stash('exclude')}  "
        . "@{$c->stash('directories')} | /usr/bin/gzip $clvl ";
    %>
</div>
```

## Troubleshooting

If you encounter issues with perltidy, the formatter will fall back to a simple indentation-based formatter for Perl code. Enable debug logging with the `--debug` flag to see detailed information about the formatting process.

## License

This software is provided as-is, without any warranties or conditions of any kind.