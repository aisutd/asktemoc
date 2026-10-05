# AskTemoc_Backend

---

### Requirements

- Python 3.13+
- [`ollama`](https://ollama.com/) installed and running (for future integration, currently mocked)
- `pip` (Python package installer)
- Git

---

### Clone the Repository

```bash
git clone https://github.com/Conwenu/AskTemoc_Backend.git
cd path/to/project-root
```

---

### Install Dependencies

Make sure you're in a **virtual environment**:

```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

Install required packages:

```bash
pip install -r requirements.txt
```

---

### Make Sure Ollama is Installed

Ensure [`ollama`](https://ollama.com/) is installed and running locally.

```bash
ollama run llama3  # Or any other model you plan to use
```

---

### Run the FastAPI Server

You can start the server using:

```bash
uvicorn app.main:app --reload
```

- Visit Swagger UI: [http://localhost:8000/docs](http://localhost:8000/docs)

---

### Test the `/api/query` Endpoint

You can test using **curl**, **Thunder Client Extension**, **Postman**, or directly in Swagger UI.

**Endpoint:** `GET /api/query/`

**Query Parameter:** `query`

#### Example Request

Using **curl**:

```bash
curl -X POST "http://127.0.0.1:8000/api/query/" \
  -H "Content-Type: application/json" \
  -d '{"query": "What is FastAPI?"}'
```

#### Example Response

```json
{
  "answer": "Answer: What is FastAPI?"
}
```

Or if you have successfully installed `Ollama` with the `llama3.1:8b` model

```json
{
  "answer": "The capital of China is Beijing."
}
```

---


### Webscraper Setup
If you haven’t already installed the **Crawl4AI** library (it should be listed in `requirements.txt`), run:

```bash
pip install crawl4ai
```

After installing dependencies, run:

```bash
crawl4ai-setup
```

Then verify the installation with:

```bash
crawl4ai-doctor
```