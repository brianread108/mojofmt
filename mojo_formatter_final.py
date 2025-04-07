#!/usr/bin/env python3
"""
Mojolicious Template Formatter

This program formats Mojolicious template files to make their structure
easily understandable by humans. It properly indents HTML tags, Mojolicious
commands, helper commands, and Perl constructs.

Uses perltidy for formatting embedded Perl code and can output perltidy results
to a separate file for inspection.
"""

import re
import sys
import argparse
import subprocess
import tempfile
import os
import logging
import uuid
import platform


# Version information
VERSION = "1.0"
PROGRAM_NAME = "Mojolicious Template Formatter"

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stderr)
    ]
)
logger = logging.getLogger('mojo_formatter')


def get_python_version():
    """Get the current Python version."""
    return f"{platform.python_version()}"


def get_perltidy_version():
    """Get the installed perltidy version."""
    try:
        # Run the perltidy command
        result = subprocess.run(['perltidy', '-v'], capture_output=True, text=True)
        if result.returncode == 0:
            # Extract version from stdout
            version_match = re.search(r'This is perltidy, (v[\d\.]+)', result.stdout)
            if version_match:
                return version_match.group(1)
            return "Unknown version"
        else:
            return "Not available"
    except Exception:
        return "Not installed"
                
def log_system_info():
    """Log system information including program version and dependencies."""
    python_version = get_python_version()
    perltidy_version = get_perltidy_version()
    
    logger.info(f"{PROGRAM_NAME} v{VERSION}")
    logger.info(f"Running with Python {python_version}")
    logger.info(f"Perltidy {perltidy_version}")

class MojoTemplateFormatter:
    """
    A formatter for Mojolicious template files that makes their structure
    easily understandable by humans.
    """

    def __init__(self, indent_size=4, perltidy_output_dir=None):
        """Initialize the formatter with default settings."""
        self.indent_size = indent_size
        self.current_indent = 0
        self.output_lines = []
        self.perl_block_stack = []
        self.html_tag_stack = []
        self.in_form_block = False
        self.in_content_block = False
        self.remove_blank_lines = True
        self.perltidy_output_dir = perltidy_output_dir
        self.perltidy_block_count = 0
        
        # Patterns for Mojolicious syntax
        self.mojo_command_pattern = re.compile(r'^(\s*)(%\s*.*?)$')
        self.perl_block_start_pattern = re.compile(r'%\s*(?:if|for|while|unless|begin)\b.*?{')
        self.perl_if_pattern = re.compile(r'%\s*if\s*\(.*\)\s*{')
        self.content_block_start_pattern = re.compile(r'%\s*content_for\b.*?=>\s*begin\b')
        self.form_block_start_pattern = re.compile(r'%=\s*form_for\b.*?=>\s*begin\b')
        self.perl_block_end_pattern = re.compile(r'%\s*}')
        self.perl_end_pattern = re.compile(r'%\s*end\b')
        
        # Embedded Perl patterns
        self.embedded_perl_start_pattern = re.compile(r'<%')
        self.embedded_perl_end_pattern = re.compile(r'%>')
        self.mojo_expression_pattern = re.compile(r'<%=?=?\s*(.*?)\s*%>')
        self.mojo_code_pattern = re.compile(r'<%\s*(.*?)\s*%>')
        self.mojo_comment_pattern = re.compile(r'<%#\s*(.*?)\s*%>')
        
        # HTML tag patterns
        self.html_open_tag_pattern = re.compile(r'<([a-zA-Z][a-zA-Z0-9]*)[^>]*(?<!/)>')
        self.html_close_tag_pattern = re.compile(r'</([a-zA-Z][a-zA-Z0-9]*)>')
        self.html_self_closing_tag_pattern = re.compile(r'<([a-zA-Z][a-zA-Z0-9]*)[^>]*/>')
        
        # Pattern for multiple closing tags on a line
        self.multiple_closing_tags_pattern = re.compile(r'(</[^>]+>)(\s*)(</[^>]+>)')
        
        # List of tags that shouldn't cause indentation changes
        self.non_indenting_tags = ['br', 'hr', 'img', 'input', 'link', 'meta']
        
        # List of tags that should have minimal indentation
        self.minimal_indent_tags = ['span', 'p']
        
        # Pattern for lines with multiple closing tags
        self.multiple_close_tags_pattern = re.compile(r'</[^>]+>.*</[^>]+>')
        
        # Pattern for lines ending with <br> and closing tags
        self.br_with_close_tags_pattern = re.compile(r'<br[^>]*>\s*</[^>]+>')
        
        # Pattern for lines with <br></span></p> pattern or variations
        self.br_span_p_pattern = re.compile(r'<br[^>]*>\s*</span>\s*</p>')
        
        # Pattern for lines with <br></span> followed by whitespace and </p>
        self.br_span_space_p_pattern = re.compile(r'<br[^>]*>\s*</span>\s+</p>')

    def format(self, content):
        """
        Format the given Mojolicious template content.
        
        Args:
            content (str): The content of the Mojolicious template file.
            
        Returns:
            str: The formatted content.
        """
        logger.info("Starting formatting process")
        
        # First pass: process embedded Perl blocks
        logger.info("Processing embedded Perl blocks")
        content = self._preprocess_embedded_perl(content)
        
        lines = content.splitlines()
        self.output_lines = []
        self.current_indent = 0
        self.perl_block_stack = []
        self.html_tag_stack = []
        self.in_form_block = False
        self.in_content_block = False
        
        logger.info("Processing lines for HTML and Mojolicious commands")
        i = 0
        while i < len(lines):
            line = lines[i]
            i += 1
            
            # Skip empty lines if remove_blank_lines is enabled
            if not line.strip():
                if not self.remove_blank_lines:
                    self.output_lines.append('')
                continue
                
            # Process the line based on its type
            if self._is_mojo_command_line(line):
                self._process_mojo_command_line(line)
            else:
                self._process_html_line(line)
        
        # Second pass: handle closing tags on separate lines
        logger.info("Post-processing closing tags")
        self._postprocess_closing_tags()
        
        logger.info("Formatting complete")
        return '\n'.join(self.output_lines)
    
    def _preprocess_embedded_perl(self, content):
        """
        Preprocess embedded Perl blocks to format the Perl code inside using perltidy.
        
        Args:
            content (str): The content to preprocess.
            
        Returns:
            str: The preprocessed content.
        """
        # Find all embedded Perl blocks
        pattern = re.compile(r'<%\s*(.*?)\s*%>', re.DOTALL)
        
        def format_perl_code(match):
            perl_code = match.group(1)
            if not perl_code.strip():
                logger.debug("Empty Perl block found")
                return f"<%\n%>"
                
            # Format the Perl code by adding indentation
            lines = perl_code.splitlines()
            if len(lines) <= 1:
                # For single-line Perl, just clean up spacing
                logger.debug("Single-line Perl block found")
                return f"<% {perl_code.strip()} %>"
                
            # For multi-line Perl, use perltidy
            self.perltidy_block_count += 1
            block_id = self.perltidy_block_count
            logger.info(f"Found multi-line Perl block #{block_id} with {len(lines)} lines")
            logger.debug(f"Original Perl code (block #{block_id}):\n{perl_code}")
            
            formatted_perl = self._run_perltidy(perl_code, block_id)
            
            # If perltidy fails, fall back to our simple formatter
            if formatted_perl is None:
                logger.warning(f"Perltidy failed for block #{block_id}, falling back to simple formatter")
                formatted_lines = []
                current_indent = self.indent_size
                
                for line in lines:
                    if not line.strip():
                        continue  # Skip empty lines
                    
                    stripped = line.lstrip()
                    
                    # Check if this line decreases indentation (closing brace at start)
                    if stripped.startswith('}') or stripped.startswith(');'):
                        current_indent = max(self.indent_size, current_indent - self.indent_size)
                    
                    # Add the line with proper indentation
                    if stripped.startswith('#'):
                        # For comments, use the current indentation
                        formatted_lines.append(' ' * current_indent + stripped)
                    else:
                        formatted_lines.append(' ' * current_indent + stripped)
                    
                    # Check if this line increases indentation for the next line
                    if (stripped.endswith('{') or 
                        stripped.endswith('({') or 
                        stripped.endswith('sub {') or 
                        stripped.endswith('= {') or
                        stripped.endswith('=> {') or
                        (stripped.endswith('(') and not stripped.startswith(')'))):
                        current_indent += self.indent_size
                    
                    # Special case for closing parentheses that decrease indentation
                    if stripped.endswith(');') and not stripped.startswith('('):
                        current_indent = max(self.indent_size, current_indent - self.indent_size)
                
                # Join the formatted lines with newlines
                formatted_perl = '\n'.join(formatted_lines)
            else:
                logger.info(f"Perltidy successfully formatted block #{block_id}")
                logger.debug(f"Perltidy formatted code (block #{block_id}):\n{formatted_perl}")
                
            # Note: No space between % and > in the closing tag
            # IMPORTANT: Preserve the exact perltidy formatting
            return f"<%\n{formatted_perl}\n%>"
        
        # Replace all embedded Perl blocks with formatted versions
        logger.info("Searching for embedded Perl blocks")
        result = pattern.sub(format_perl_code, content)
        logger.info(f"Embedded Perl block processing complete, found {self.perltidy_block_count} blocks")
        return result
    
    def _run_perltidy(self, perl_code, block_id):
        """
        Run perltidy on the given Perl code.
        
        Args:
            perl_code (str): The Perl code to format.
            block_id (int): Identifier for this Perl block.
            
        Returns:
            str: The formatted Perl code, or None if perltidy fails.
        """
        try:
            logger.info(f"Running perltidy on Perl block #{block_id}")
            
            # Create temporary files for input and output
            with tempfile.NamedTemporaryFile(mode='w+', delete=False) as input_file:
                input_file.write(perl_code)
                input_file_path = input_file.name
                logger.debug(f"Created temporary input file for block #{block_id}: {input_file_path}")
            
            output_file_path = input_file_path + '.tidy'
            
            # Run perltidy with our desired options
            cmd = [
                'perltidy',
                '-i=' + str(self.indent_size),  # Set indentation size
                '-ci=' + str(self.indent_size), # Set continuation indentation
                '-l=120',                       # Line length
                '-pt=2',                        # Parenthesis tightness
                '-bt=2',                        # Brace tightness
                '-sbt=2',                       # Square bracket tightness
                '-ce',                          # Cuddled else
                '-nbl',                         # No blank lines before comments
                '-nsfs',                        # No space for semicolon
                input_file_path,                # Input file
                '-o', output_file_path          # Output file
            ]
            
            logger.debug(f"Executing perltidy command for block #{block_id}: {' '.join(cmd)}")
            
            # Execute perltidy
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            # Check if perltidy succeeded
            if result.returncode != 0:
                logger.error(f"Perltidy failed for block #{block_id} with return code {result.returncode}")
                logger.error(f"Stderr: {result.stderr}")
                return None
            
            # Read the formatted code
            if os.path.exists(output_file_path):
                with open(output_file_path, 'r') as output_file:
                    formatted_code = output_file.read()
                    logger.info(f"Perltidy output file size for block #{block_id}: {len(formatted_code)} bytes")
                    
                    # If requested, save the perltidy output to a separate file
                    if self.perltidy_output_dir:
                        self._save_perltidy_output(perl_code, formatted_code, block_id)
            else:
                logger.error(f"Perltidy output file not found for block #{block_id}: {output_file_path}")
                return None
            
            # Clean up temporary files
            logger.debug(f"Cleaning up temporary files for block #{block_id}")
            os.unlink(input_file_path)
            if os.path.exists(output_file_path):
                os.unlink(output_file_path)
            
            return formatted_code.strip()
            
        except Exception as e:
            logger.exception(f"Error running perltidy for block #{block_id}: {e}")
            return None
    
    def _save_perltidy_output(self, original_code, formatted_code, block_id):
        """
        Save the original and formatted Perl code to separate files for inspection.
        
        Args:
            original_code (str): The original Perl code.
            formatted_code (str): The formatted Perl code.
            block_id (int): Identifier for this Perl block.
        """
        try:
            # Create the output directory if it doesn't exist
            os.makedirs(self.perltidy_output_dir, exist_ok=True)
            
            # Create filenames for the original and formatted code
            original_file = os.path.join(self.perltidy_output_dir, f"perl_block_{block_id}_original.pl")
            formatted_file = os.path.join(self.perltidy_output_dir, f"perl_block_{block_id}_formatted.pl")
            
            # Write the original code to a file
            with open(original_file, 'w') as f:
                f.write(original_code)
                
            # Write the formatted code to a file
            with open(formatted_file, 'w') as f:
                f.write(formatted_code)
                
            logger.info(f"Saved perltidy input/output for block #{block_id} to {original_file} and {formatted_file}")
            
        except Exception as e:
            logger.exception(f"Error saving perltidy output for block #{block_id}: {e}")
    
    def _postprocess_closing_tags(self):
        """
        Postprocess the output lines to put closing tags on separate lines.
        """
        logger.info("Post-processing closing tags")
        result_lines = []
        i = 0
        
        # Track if we're inside an embedded Perl block
        in_perl_block = False
        
        while i < len(self.output_lines):
            line = self.output_lines[i]
            
            # Check if we're entering an embedded Perl block
            if line.strip() == '<%':
                in_perl_block = True
                result_lines.append(line)
                i += 1
                continue
                
            # Check if we're exiting an embedded Perl block
            if line.strip() == '%>':
                in_perl_block = False
                result_lines.append(line)
                i += 1
                continue
                
            # If we're inside an embedded Perl block, don't modify the line
            if in_perl_block:
                result_lines.append(line)
                i += 1
                continue
            
            # Check for multiple closing tags
            if self.multiple_closing_tags_pattern.search(line):
                logger.debug(f"Found multiple closing tags in line: {line}")
                # Split the line at each closing tag
                parts = []
                current = line
                
                while self.multiple_closing_tags_pattern.search(current):
                    match = self.multiple_closing_tags_pattern.search(current)
                    first_tag = match.group(1)
                    whitespace = match.group(2)
                    second_tag = match.group(3)
                    
                    # Split at the second tag
                    before_second = current[:match.start(3)]
                    after_second = current[match.end(3):]
                    
                    # Add the part before the second tag
                    parts.append(before_second)
                    
                    # Update current to be the second tag and everything after
                    current = second_tag + after_second
                
                # Add the last part
                if current:
                    parts.append(current)
                
                # Add all parts as separate lines
                base_indent = len(line) - len(line.lstrip())
                for j, part in enumerate(parts):
                    # For closing tags, reduce indentation
                    if j > 0 and part.strip().startswith('</'):
                        indent = max(0, base_indent - self.indent_size)
                    else:
                        indent = base_indent
                        
                    result_lines.append(' ' * indent + part.strip())
                    logger.debug(f"Split line part {j+1}: {' ' * indent + part.strip()}")
            else:
                result_lines.append(line)
                
            i += 1
            
        self.output_lines = result_lines
        logger.info(f"Post-processing complete, {len(result_lines)} lines in output")
    
    def _is_mojo_command_line(self, line):
        """
        Check if the line is a Mojolicious command line (starts with %).
        
        Args:
            line (str): The line to check.
            
        Returns:
            bool: True if the line is a Mojolicious command line, False otherwise.
        """
        stripped = line.lstrip()
        return stripped and stripped[0] == '%'
    
    def _process_mojo_command_line(self, line):
        """
        Process a Mojolicious command line.
        
        Args:
            line (str): The Mojolicious command line to process.
        """
        stripped = line.lstrip()
        logger.debug(f"Processing Mojo command line: {stripped}")
        
        # Ensure space after % if not followed by specific characters
        if stripped.startswith('%') and len(stripped) > 1 and stripped[1] not in ['=', '#', '%']:
            if not stripped[1].isspace():
                stripped = '%' + ' ' + stripped[1:]
        
        # Check for content block start
        if self.content_block_start_pattern.search(stripped):
            logger.debug("Found content block start")
            indent = ' ' * self.current_indent
            formatted_line = indent + stripped
            self.output_lines.append(formatted_line)
            self.in_content_block = True
            self.current_indent += self.indent_size
            return
            
        # Check for form block start
        if self.form_block_start_pattern.search(stripped):
            logger.debug("Found form block start")
            indent = ' ' * self.current_indent
            formatted_line = indent + stripped
            self.output_lines.append(formatted_line)
            self.in_form_block = True
            self.current_indent += self.indent_size
            return
        
        # Handle Perl block opening
        if self.perl_block_start_pattern.search(stripped):
            logger.debug("Found Perl block start")
            indent = ' ' * self.current_indent
            formatted_line = indent + stripped
            self.output_lines.append(formatted_line)
            
            # Track the block with its opening indentation level
            self.perl_block_stack.append(self.current_indent)
            self.current_indent += self.indent_size
            return
            
        # Handle Perl block closing with }
        if self.perl_block_end_pattern.search(stripped):
            logger.debug("Found Perl block end with }")
            if self.perl_block_stack:
                # Pop the indentation level from the stack
                self.current_indent = self.perl_block_stack.pop()
                
                # Apply the indentation to the closing brace (same as opening)
                indent = ' ' * self.current_indent
                formatted_line = indent + stripped
                self.output_lines.append(formatted_line)
            else:
                # If no block stack, just use current indentation
                indent = ' ' * self.current_indent
                formatted_line = indent + stripped
                self.output_lines.append(formatted_line)
            return
            
        # Handle Perl block closing with end
        if self.perl_end_pattern.search(stripped):
            logger.debug("Found Perl block end with 'end'")
            if self.in_form_block and not self.perl_block_stack:
                self.in_form_block = False
                self.current_indent = max(0, self.current_indent - self.indent_size)
            elif self.in_content_block and not self.perl_block_stack:
                self.in_content_block = False
                self.current_indent = max(0, self.current_indent - self.indent_size)
            elif self.perl_block_stack:
                # Pop the indentation level from the stack
                self.current_indent = self.perl_block_stack.pop()
            
            # Apply the indentation to the end statement
            indent = ' ' * self.current_indent
            formatted_line = indent + stripped
            self.output_lines.append(formatted_line)
            return
                
        # Regular Mojolicious command line
        indent = ' ' * self.current_indent
        formatted_line = indent + stripped
        self.output_lines.append(formatted_line)
    
    def _process_html_line(self, line):
        """
        Process an HTML line.
        
        Args:
            line (str): The HTML line to process.
        """
        # Special handling for embedded Perl blocks
        if line.strip().startswith('<%'):
            # For embedded Perl blocks, don't modify the indentation
            # Just add the line as is to preserve perltidy formatting
            self.output_lines.append(line)
            return
            
        # Special handling for Perl block closing tag
        if line.strip() == '%>':
            # For the closing tag, don't add any space after %
            self.output_lines.append('%>')
            return
            
        stripped = line.lstrip()
        logger.debug(f"Processing HTML line: {stripped[:30]}...")
        
        # Special handling for lines with <br></span></p> pattern or variations
        if self.br_span_p_pattern.search(stripped) or self.br_span_space_p_pattern.search(stripped):
            logger.debug("Found <br></span></p> pattern")
            # Find the base indentation level for this paragraph
            base_indent = 0
            for i in range(len(self.html_tag_stack)):
                if i < len(self.html_tag_stack) and self.html_tag_stack[i].lower() == 'p':
                    base_indent = i * self.indent_size
                    break
            
            # If we couldn't find a p tag, use the current indentation minus some offset
            if base_indent == 0:
                base_indent = max(0, self.current_indent - (2 * self.indent_size))
                
            # Format the line with the base indentation
            indent = ' ' * base_indent
            
            # Preserve the original spacing between </span> and </p> if it exists
            if self.br_span_space_p_pattern.search(stripped):
                # Replace <br></span> with <br></span> but keep the spacing before </p>
                parts = re.split(r'(</span>\s+</p>)', stripped)
                if len(parts) >= 3:
                    formatted_line = indent + parts[0] + parts[1]
                else:
                    formatted_line = indent + stripped
            else:
                formatted_line = indent + stripped
                
            self.output_lines.append(formatted_line)
            
            # Update the tag stack to reflect the closing tags
            if 'span' in self.html_tag_stack:
                self.html_tag_stack.remove('span')
            if 'p' in self.html_tag_stack:
                self.html_tag_stack.remove('p')
                
            # Adjust current indentation
            self.current_indent = base_indent
            
            return
        
        # Special handling for lines with <br> and closing tags
        if self.br_with_close_tags_pattern.search(stripped):
            logger.debug("Found <br> with closing tags")
            # Find appropriate indentation level
            indent_level = self.current_indent
            for tag in self.html_close_tag_pattern.findall(stripped):
                if tag.lower() in self.minimal_indent_tags and tag.lower() in [t.lower() for t in self.html_tag_stack]:
                    indent_level = max(0, indent_level - (self.indent_size // 2))
            
            indent = ' ' * indent_level
            formatted_line = indent + stripped
            self.output_lines.append(formatted_line)
            
            # Update the tag stack to reflect the closing tags
            close_tags = self.html_close_tag_pattern.findall(stripped)
            for tag in close_tags:
                if tag.lower() in [t.lower() for t in self.html_tag_stack]:
                    self.html_tag_stack.remove(tag)
            
            return
        
        # Skip indentation changes for lines with only non-indenting tags
        if self._contains_only_non_indenting_tags(stripped):
            logger.debug("Found line with only non-indenting tags")
            indent = ' ' * self.current_indent
            formatted_line = indent + stripped
            self.output_lines.append(formatted_line)
            return
            
        # Special handling for lines with multiple closing tags
        if self.multiple_close_tags_pattern.search(stripped):
            logger.debug("Found line with multiple closing tags")
            # Count the number of closing tags
            close_count = len(self.html_close_tag_pattern.findall(stripped))
            # Reduce indentation once for the whole line
            if close_count > 1 and self.html_tag_stack:
                for _ in range(min(close_count, len(self.html_tag_stack))):
                    tag = self.html_tag_stack.pop()
                    if tag.lower() not in self.non_indenting_tags:
                        self.current_indent = max(0, self.current_indent - self.indent_size)
            
            indent = ' ' * self.current_indent
            formatted_line = indent + stripped
            self.output_lines.append(formatted_line)
            return
        
        # Check for closing tags first to adjust indentation before adding the line
        close_tags = self.html_close_tag_pattern.findall(stripped)
        for tag in close_tags:
            if tag.lower() in self.non_indenting_tags:
                continue
                
            if tag.lower() in [t.lower() for t in self.html_tag_stack]:
                self.html_tag_stack.remove(tag)
                
                # Use smaller indentation for minimal indent tags
                if tag.lower() in self.minimal_indent_tags:
                    self.current_indent = max(0, self.current_indent - (self.indent_size // 2))
                else:
                    self.current_indent = max(0, self.current_indent - self.indent_size)
        
        # Apply current indentation
        indent = ' ' * self.current_indent
        formatted_line = indent + stripped
        self.output_lines.append(formatted_line)
        
        # Check for opening tags to adjust indentation for next lines
        open_tags = self.html_open_tag_pattern.findall(stripped)
        self_closing_tags = self.html_self_closing_tag_pattern.findall(stripped)
        
        # Add only non-self-closing tags to the stack (excluding special tags)
        for tag in open_tags:
            if tag.lower() in self.non_indenting_tags:
                continue
                
            if tag not in self_closing_tags:
                self.html_tag_stack.append(tag)
                
                # Use smaller indentation for minimal indent tags
                if tag.lower() in self.minimal_indent_tags:
                    self.current_indent += (self.indent_size // 2)
                else:
                    self.current_indent += self.indent_size
    
    def _contains_only_non_indenting_tags(self, line):
        """
        Check if the line contains only non-indenting tags.
        
        Args:
            line (str): The line to check.
            
        Returns:
            bool: True if the line contains only non-indenting tags, False otherwise.
        """
        # Check for <br> tags
        for tag in self.non_indenting_tags:
            pattern = re.compile(f'<{tag}[^>]*>')
            if pattern.search(line):
                # If the line has a non-indenting tag and not much else
                other_content = re.sub(f'</?{tag}[^>]*>', '', line).strip()
                if not other_content or other_content == '</span>' or other_content == '</p>' or '</span>' in other_content:
                    return True
                
        return False


def format_mojolicious_template(content, indent_size=4, remove_blank_lines=True, log_level=logging.INFO, perltidy_output_dir=None):
    """
    Format a Mojolicious template.
    
    Args:
        content (str): The content of the Mojolicious template.
        indent_size (int): Number of spaces to use for indentation.
        remove_blank_lines (bool): Whether to remove blank lines.
        log_level (int): Logging level to use.
        perltidy_output_dir (str): Directory to save perltidy input/output files.
        
    Returns:
        str: The formatted content.
    """
    # Set the logging level
    logger.setLevel(log_level)
    
    formatter = MojoTemplateFormatter(indent_size, perltidy_output_dir)
    formatter.remove_blank_lines = remove_blank_lines
    return formatter.format(content)


def main():
    """Main function to run the formatter."""
    parser = argparse.ArgumentParser(description='Format Mojolicious template files.')
    parser.add_argument('input_file', nargs='?', type=argparse.FileType('r'),
                        default=sys.stdin, help='Input file (default: stdin)')
    parser.add_argument('output_file', nargs='?', type=argparse.FileType('w'),
                        default=sys.stdout, help='Output file (default: stdout)')
    parser.add_argument('--indent', type=int, default=4,
                        help='Number of spaces to use for indentation (default: 4)')
    parser.add_argument('--keep-blank-lines', action='store_true',
                        help='Keep blank lines in the output (default: remove blank lines)')
    parser.add_argument('--log-level', choices=['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'],
                        default='INFO', help='Set the logging level (default: INFO)')
    parser.add_argument('--perltidy-output-dir', type=str,
                        help='Directory to save perltidy input/output files for inspection')
    args = parser.parse_args()
    
    # Set the log level based on the command-line argument
    log_level = getattr(logging, args.log_level)
    logger.setLevel(log_level)
    
    # Log program and version information
    log_system_info()
 
    logger.info(f"Starting formatter with indent={args.indent}, keep_blank_lines={args.keep_blank_lines}, log_level={args.log_level}")
    if args.perltidy_output_dir:
        logger.info(f"Perltidy output will be saved to: {args.perltidy_output_dir}")
    
    content = args.input_file.read()
    logger.info(f"Read {len(content)} bytes from input")
    
    formatted_content = format_mojolicious_template(
        content, 
        args.indent, 
        remove_blank_lines=not args.keep_blank_lines,
        log_level=log_level,
        perltidy_output_dir=args.perltidy_output_dir
    )
    
    logger.info(f"Writing {len(formatted_content)} bytes to output")
    args.output_file.write(formatted_content)
    logger.info("Formatting complete")


if __name__ == '__main__':
    main()