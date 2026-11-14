# Third-party notices

## ILIAS MCP authentication form helpers

`src/ilias_check/_ilias_form.py` adapts two narrow HTML-form operations from
`src/services/auth_service.py` in
[richmont/ilias-mcp](https://github.com/richmont/ilias-mcp), revision
`ca4f4ee5a14df65e462d87ee49e38045457f52b3`:

- choose a form containing a password input rather than an earlier search form;
- retain named input values, including hidden fields, for the form submission.

These helpers are needed to support the observed ILIAS 9_23 login layouts. The
HTTP session, credential injection, same-origin validation, redirect policy,
retry logic, and all other behavior are implemented independently. No MCP
runtime or mutation-capable service is imported.

The adapted portion is distributed under the following upstream MIT license:

```text
MIT License

Copyright (c) 2026 Deniz Altunkapan

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```
