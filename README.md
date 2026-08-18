<div align="center">

<br/>

# 🎓 sppu-academics

**Two websites. One repo. Everything an SPPU student needs.**

<br/>

[![sppucodes](https://img.shields.io/badge/sppucodes-●%20live-2ea043?style=flat-square&logo=vercel&logoColor=white)](https://sppucodes.vercel.app)&nbsp;
[![sppupyqs](https://img.shields.io/badge/sppupyqs-●%20live-0ea5e9?style=flat-square&logo=vercel&logoColor=white)](https://sppupyqs.pages.dev)&nbsp;
[![Python](https://img.shields.io/badge/Python-3.x-f59e0b?style=flat-square&logo=python&logoColor=white)](https://python.org)&nbsp;
[![Flask](https://img.shields.io/badge/Flask-framework-gray?style=flat-square&logo=flask&logoColor=white)](https://flask.palletsprojects.com)&nbsp;
[![License](https://img.shields.io/badge/license-MIT-8b5cf6?style=flat-square)](./LICENSE)

<br/>

| | Site | What it does |
|:---:|:---|:---|
| 🖥️ | [**sppucodes.vercel.app**](https://sppucodes.vercel.app) | Lab programs & code solutions for SPPU subjects |
| 📄 | [**sppupyqs.pages.dev**](https://sppupyqs.pages.dev) | Previous year question papers with exam-prep tools |
| ⚙️ | `shared/` | Worker scripts & utilities shared across both sites |

<br/>

</div>

---

## 📁 Repository Structure

This repo is a monorepo: both sites live here, along with shared utilities that power them.

```text
sppu-academics/
│
├── 📂 sppucodes/       → Programs & code solutions (Flask app)
├── 📂 sppupyqs/        → Previous year question papers (static Cloudflare Pages site)
└── 📂 shared/          → Shared workers & common utilities
```

> 🔧 The `shared/` folder contains worker logic used across both sites: background jobs, data fetching, and common helpers. See [**shared/workers/**](./shared/workers/) for the worker READMEs.

---

<br/>

## 🖥️ sppucodes — Code & Programs

> 🌐 **[sppucodes.vercel.app](https://sppucodes.vercel.app)** &nbsp;|&nbsp; 📖 [Developer breakdown →](./sppucodes/Readme.md)

`sppucodes` is a lightweight portal for SPPU lab programs and code solutions. Whether you're stuck on a DSL question at midnight or just want to cross-check your output, this site has you covered: no account, no clutter, no wait.

Browse solutions by subject directly in the browser, or skip the browser entirely and pull code straight into your terminal using the built-in API.

<br/>

**Features**

<table>
<tr>
<td width="50%">

📚 &nbsp;**Subject-wise solutions**
Solutions are organized by subject code so you can jump straight to what you need.

</td>
<td width="50%">

⚡ &nbsp;**Terminal API**
Fetch any program directly from your command line with a single `curl` command.

</td>
</tr>
<tr>
<td>

🔍 &nbsp;**Clean, readable code**
Every solution is formatted for readability: proper indentation, clear structure, and context where it helps.

</td>
<td>

🚪 &nbsp;**Zero friction**
No login. No signup. No paywalls. Open the site and start browsing immediately.

</td>
</tr>
</table>

<br/>

### 🖼️ Screenshots

<p>
  <img src="./docs/images/sppucodes_home_screen.png" width="49%" />
  &nbsp;
  <img src="./docs/images/sppucodes_view_codes.png" width="49%" />
</p>

<br/>

### 🚀 Terminal API — Get Code Without Opening a Browser

Why switch to a browser when your terminal is already open? The `sppucodes` API lets you fetch any lab solution with a single command, and prints the output directly in your terminal.

<br/>

**URL format:**

```text
https://sppucodes.vercel.app/api/{subject_code}/{question_no}
```

| Placeholder | Description | Examples |
|:---|:---|:---|
| `{subject_code}` | Short name for your subject | `cnl` &nbsp; `dsl` &nbsp; `oopl` |
| `{question_no}` | The question number you want | `1` &nbsp; `16` &nbsp; `22` |

<br/>

**Step-by-step:**

**1️⃣ &nbsp; Open Terminal**

Press the **Windows key**, type **`terminal`**, and press **Enter** to open Windows Terminal.

**2️⃣ &nbsp; Run the command**

Replace `{subject_code}` and `{question_no}` with your values, then run:

```bash
curl.exe https://sppucodes.vercel.app/api/{subject_code}/{question_no}
```

**3️⃣ &nbsp; Your code appears instantly**

The full solution is printed right in your terminal, ready to copy, run, or save.

<br/>

**Example: fetching CNL Question 16**

```bash
curl.exe https://sppucodes.vercel.app/api/cnl/16
```

> This returns the complete solution for **Computer Networks Lab (CNL)**, Question **16**, directly in your terminal.

<br/>

<div align="center">

![Terminal output showing curl command fetching CNL question 16](./docs/images/terminal_demo.png)

</div>

<br/>

### ⚙️ Run Locally

To run `sppucodes` on your machine:

```bash
cd sppucodes
python -m pip install -r requirements.txt
python app.py
```

Then open **[http://localhost:5000](http://localhost:5000)** in your browser.

<br/>

---

<br/>

## 📄 sppupyqs — Previous Year Question Papers

> 🌐 **[sppupyqs.pages.dev](https://sppupyqs.pages.dev)** &nbsp;|&nbsp; 📖 [Developer breakdown →](./sppupyqs/README.md)

`sppupyqs` is a dedicated portal for SPPU previous year question papers. Finding old papers shouldn't be a scavenger hunt: this site organizes everything cleanly, lets you view papers without downloading, and removes the watermarks that make papers hard to read. Whether you're doing a full revision or just checking which questions repeat, it's built to get out of your way and let you focus.

<br/>

**Features**

<table>
<tr>
<td width="50%">

🪟 &nbsp;**Split Layout**
Open two papers side by side in a split view and compare questions across years without juggling tabs.

</td>
<td width="50%">

📥 &nbsp;**Free Downloads**
Every paper is available to download, completely free. No account, no form, no waiting.

</td>
</tr>
<tr>
<td>

🚫 &nbsp;**Watermark Remover**
Papers are served clean, with watermarks stripped so you can read and select questions without visual noise.

</td>
<td>

👁️ &nbsp;**Direct View**
Read any paper right in the browser without downloading it. Quick reference, zero clutter.

</td>
</tr>
<tr>
<td>

📂 &nbsp;**EndSem / InSem Split**
Papers are clearly separated by exam type: EndSem and InSem.

</td>
<td>

🏷️ &nbsp;**Smart PDF Naming**
Every file follows a consistent naming format with year and month.

</td>
</tr>
</table>

<br/>

### 🖼️ Screenshots

![sppupyqs split layout showing two question papers open side by side](./docs/images/sppupqs_split_demo.png)

<br/>

<p>
  <img src="./docs/images/sppupyqs_ai_answers.png" width="49%" />
  &nbsp;
  <img src="./docs/images/sppupyqs_watermark_remove.png" width="49%" />
</p>

<br/>

### ⚙️ Run Locally

To build `sppupyqs` locally:

```bash
cd sppupyqs
python -m pip install -r requirements.txt
python build.py
```

The generated site is written to `sppupyqs/dist/`. To preview it:

```bash
cd dist
npx serve .
```

<br/>

### 🔄 Updating Manifests

The latest manifest files (JSON data for papers and subjects) are maintained in the `sppu-pyqs` branch. To update these manifests in the `main` or `test` branches, pull the `manifest` folder from the `sppu-pyqs` branch into the `sppupyqs/manifest` directory.

Run this command via Command Prompt, not PowerShell:

```cmd
cmd /c "git archive sppu-pyqs manifest | tar -x -C sppupyqs"
```

This bypasses the folder path mismatch and directly updates the files in `sppupyqs/manifest` so they are ready to be committed.

<br/>

---

<br/>

## 🔧 Workers & Shared Logic

The `shared/` directory connects both sites. It contains background workers, data-fetching utilities, and logic that would otherwise be duplicated across the two apps. Keeping it in one place means fixes and updates apply everywhere automatically.

📄 See [**shared/workers/**](./shared/workers/) for the worker READMEs and setup notes.

<br/>

---

<br/>

## 🤝 Contributing

Found a bug? A question missing? A paper that's wrong?

Feel free to open an issue or submit a pull request. Contributions that improve accuracy, add missing papers, or fix broken solutions are always welcome.

> For code contributions, please check the developer README in the relevant subfolder before making changes: [`sppucodes/Readme.md`](./sppucodes/Readme.md) or [`sppupyqs/README.md`](./sppupyqs/README.md).

<br/>

---

<br/>

## 📜 History

`sppucodes` originally handled everything: code solutions **and** question papers, all from a single site. Over time it became clear that these were two distinct tools serving different needs, so they were separated into dedicated sites with their own domains, design, and codebases.

```text
sppucodes  (original: served both codes and question papers)
    │
    ├── 🖥️  sppucodes  →  Programs & code solutions
    └── 📄  sppupyqs   →  Previous year question papers
```

The split made both sites faster to maintain, easier to improve independently, and cleaner to use.

<br/>

---

<div align="center">

<br/>

Made with ❤️ for SPPU students

<sub>If this saved you time before an exam, consider starring the repo ⭐</sub>

<br/>

[![Visit sppucodes](https://img.shields.io/badge/Visit-sppucodes-2ea043?style=for-the-badge&logo=vercel&logoColor=white)](https://sppucodes.vercel.app)&nbsp;
[![Visit sppupyqs](https://img.shields.io/badge/Visit-sppupyqs-0ea5e9?style=for-the-badge&logo=vercel&logoColor=white)](https://sppupyqs.pages.dev)

<br/>

</div>
