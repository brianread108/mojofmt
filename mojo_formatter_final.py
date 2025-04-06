#!/usr/bin/env python3
"""
Mojolicious Template Formatter

This program formats Mojolicious template files to make their structure
easily understandable by humans. It properly indents HTML tags, Mojolicious
commands, helper commands, and Perl constructs.
"""

import re
import sys
import argparse


class MojoTemplateFormatter:
    """
    A formatter for Mojolicious template files that makes their structure
    easily understandable by humans.
    """

    def __init__(self, indent_size=4):
        """Initialize the formatter with default settings."""
        self.indent_size = indent_size
        self.current_indent = 0
        self.output_lines = []
        self.perl_block_stack = []
        self.html_tag_stack = []
        self.in_form_block = False
        self.in_content_block = False
        
        # Patterns for Mojolicious syntax
        self.mojo_command_pattern = re.compile(r'^(\s*)(%\s*.*?)$')
        self.perl_block_start_pattern = re.compile(r'%\s*(?:if|for|while|unless|begin)\b.*?{')
        self.perl_if_pattern = re.compile(r'%\s*if\s*\(.*\)\s*{')
        self.content_block_start_pattern = re.compile(r'%\s*content_for\b.*?=>\s*begin\b')
        self.form_block_start_pattern = re.compile(r'%=\s*form_for\b.*?=>\s*begin\b')
        self.perl_block_end_pattern = re.compile(r'%\s*}')
        self.perl_end_pattern = re.compile(r'%\s*end\b')
        self.mojo_expression_pattern = re.compile(r'<%=?=?\s*(.*?)\s*%>')
        self.mojo_code_pattern = re.compile(r'<%\s*(.*?)\s*%>')
        self.mojo_comment_pattern = re.compile(r'<%#\s*(.*?)\s*%>')
        
        # HTML tag patterns
        self.html_open_tag_pattern = re.compile(r'<([a-zA-Z][a-zA-Z0-9]*)[^>]*(?<!/)>')
        self.html_close_tag_pattern = re.compile(r'</([a-zA-Z][a-zA-Z0-9]*)>')
        self.html_self_closing_tag_pattern = re.compile(r'<([a-zA-Z][a-zA-Z0-9]*)[^>]*/>')
        
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
        lines = content.splitlines()
        self.output_lines = []
        self.current_indent = 0
        self.perl_block_stack = []
        self.html_tag_stack = []
        self.in_form_block = False
        self.in_content_block = False
        
        i = 0
        while i < len(lines):
            line = lines[i]
            i += 1
            
            # Skip empty lines
            if not line.strip():
                self.output_lines.append('')
                continue
                
            # Process the line based on its type
            if self._is_mojo_command_line(line):
                self._process_mojo_command_line(line)
            else:
                self._process_html_line(line)
                
        return '\n'.join(self.output_lines)
    
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
        
        # Ensure space after % if not followed by specific characters
        if stripped.startswith('%') and len(stripped) > 1 and stripped[1] not in ['=', '#', '%']:
            if not stripped[1].isspace():
                stripped = '%' + ' ' + stripped[1:]
        
        # Check for content block start
        if self.content_block_start_pattern.search(stripped):
            indent = ' ' * self.current_indent
            formatted_line = indent + stripped
            self.output_lines.append(formatted_line)
            self.in_content_block = True
            self.current_indent += self.indent_size
            return
            
        # Check for form block start
        if self.form_block_start_pattern.search(stripped):
            indent = ' ' * self.current_indent
            formatted_line = indent + stripped
            self.output_lines.append(formatted_line)
            self.in_form_block = True
            self.current_indent += self.indent_size
            return
        
        # Handle Perl block opening
        if self.perl_block_start_pattern.search(stripped):
            indent = ' ' * self.current_indent
            formatted_line = indent + stripped
            self.output_lines.append(formatted_line)
            
            # Track the block with its opening indentation level
            self.perl_block_stack.append(self.current_indent)
            self.current_indent += self.indent_size
            return
            
        # Handle Perl block closing with }
        if self.perl_block_end_pattern.search(stripped):
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
        stripped = line.lstrip()
        
        # Special handling for lines with <br></span></p> pattern or variations
        if self.br_span_p_pattern.search(stripped) or self.br_span_space_p_pattern.search(stripped):
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
            indent = ' ' * self.current_indent
            formatted_line = indent + stripped
            self.output_lines.append(formatted_line)
            return
            
        # Special handling for lines with multiple closing tags
        if self.multiple_close_tags_pattern.search(stripped):
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


def format_mojolicious_template(content, indent_size=4):
    """
    Format a Mojolicious template.
    
    Args:
        content (str): The content of the Mojolicious template.
        indent_size (int): Number of spaces to use for indentation.
        
    Returns:
        str: The formatted content.
    """
    formatter = MojoTemplateFormatter(indent_size)
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
    args = parser.parse_args()
    
    content = args.input_file.read()
    formatted_content = format_mojolicious_template(content, args.indent)
    args.output_file.write(formatted_content)


if __name__ == '__main__':
    main()