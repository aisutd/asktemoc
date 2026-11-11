"""
embedding_coverage.py — PCA/UMAP topic-coverage check on the corpus embeddings in Neon.

Pulls every chunk embedding, labels each by topic area (from the program folder name),
projects with PCA and UMAP, and compares each topic's share of the corpus with its share
of eval-question target docs. Writes plots and coverage_summary.json to backend/analysis/.

Usage (crawl4ai-env activated):
    python backend/embedding_coverage.py
"""

import json
import os
import re
from collections import Counter
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import psycopg2
import umap
from dotenv import load_dotenv
from sklearn.cluster import KMeans
from sklearn.decomposition import PCA

HERE = Path(__file__).parent
OUT = HERE / "analysis"
OUT.mkdir(exist_ok=True)
load_dotenv(HERE / ".env")

# First matching rule wins.
TOPIC_RULES = [
    ("Catalog overview", r"^undergraduate_catalog_overview/"),
    ("Web pages (non-catalog)", r"^web/"),
    ("Double majors", r"double_major"),
    ("Education & interdisciplinary", r"education|interdisciplinary|healthcare_studies"),
    ("Engineering & CS", r"computer_science|computer_engineering|electrical|mechanical|software_eng|systems_eng|biomedical_engineering|data_science|cyber_defense|nanoscience|semiconductor|sustainable_energy"),
    ("Business", r"accounting|finance|marketing|business|supply_chain|human_resource|healthcare_management|information_systems|innovation_and_entrepreneurship|cybersecurity_and_risk"),
    ("Natural sciences & math", r"biology|chemistry|mathematics|physics|actuarial|biochemistry|biomedical_sciences|geosciences|molecular|quantum|geophysics|sustainable_earth|biomedical_data|biomedical_analytics"),
    ("Behavioral & brain sciences", r"child_learning|cognitive|neuroscience|psychology|speech|behavioral_research|biobehavioral|user_experience|ux_research|neural_net"),
    ("Econ, policy & social science", r"criminology|economics|political|public_health|sociology|geospatial|public_affairs|public_policy|sustainability_planning|compassionate|civic|military|nonprofit"),
    ("Arts, humanities & media", r"animation|media_arts|history|latin|literature|philosophy|visual_and_performing|professional_communication|creative_writing|holocaust|legal_research|intercultural|american_studies|applied_experience"),
]


def topic_of(program: str) -> str:
    for name, pat in TOPIC_RULES:
        if re.search(pat, program):
            return name
    return "Other"


def load_embeddings():
    conn = psycopg2.connect(os.environ["DATABASE_URL"])
    cur = conn.cursor()
    cur.execute(
        """
        SELECT d.title, c.chunk_index, e.vector::text
        FROM embeddings e
        JOIN chunks c ON c.id = e.chunk_id
        JOIN documents d ON d.id = c.document_id
        ORDER BY d.title, c.chunk_index;
        """
    )
    rows = cur.fetchall()
    conn.close()
    titles = [r[0] for r in rows]
    X = np.array([json.loads(r[2]) for r in rows], dtype=np.float32)
    return titles, X


def eval_targets():
    """Program folders named as target docs in eval_questions.md."""
    text = (HERE / "eval_questions.md").read_text()
    targets = []
    for line in text.splitlines():
        if line.startswith("*Target doc"):
            targets += re.findall(r"`([a-z0-9_]+)/", line)
    return targets


def main():
    titles, X = load_embeddings()
    programs = [t.split("/")[0] for t in titles]
    kinds = [t.split("/")[1] if "/" in t else "" for t in titles]
    topics = np.array([topic_of(p + "/") for p in programs])
    print(f"{len(X)} chunks, {len(set(programs))} programs, dim={X.shape[1]}")

    pca = PCA(n_components=2, random_state=0)
    P = pca.fit_transform(X)
    U = umap.UMAP(n_neighbors=15, min_dist=0.1, metric="cosine", random_state=0).fit_transform(X)

    names = sorted(set(topics))
    cmap = plt.get_cmap("tab10")
    colors = {n: cmap(i) for i, n in enumerate(names)}

    fig, axes = plt.subplots(1, 2, figsize=(17, 7))
    for ax, Z, title in [
        (axes[0], P, f"PCA ({pca.explained_variance_ratio_.sum():.0%} variance in 2 PCs)"),
        (axes[1], U, "UMAP (cosine)"),
    ]:
        for n in names:
            m = topics == n
            ax.scatter(Z[m, 0], Z[m, 1], s=14, alpha=0.7, color=colors[n], label=f"{n} ({m.sum()})")
        ax.set_title(title)
        ax.set_xticks([]); ax.set_yticks([])
    axes[1].legend(loc="center left", bbox_to_anchor=(1.01, 0.5), fontsize=9, frameon=False)
    fig.suptitle("AskTemoc corpus embeddings by topic area (text-embedding-3-small)")
    fig.tight_layout()
    fig.savefig(OUT / "embedding_map.png", dpi=140, bbox_inches="tight")
    plt.close(fig)

    # Unsupervised clusters on UMAP, to see whether topics form their own regions.
    k = 12
    km = KMeans(n_clusters=k, n_init=10, random_state=0).fit(U)
    fig, ax = plt.subplots(figsize=(10, 8))
    sc = ax.scatter(U[:, 0], U[:, 1], c=km.labels_, cmap="tab20", s=14, alpha=0.8)
    for c in range(k):
        m = km.labels_ == c
        top = Counter(topics[m]).most_common(1)[0][0]
        cx, cy = U[m].mean(axis=0)
        ax.annotate(f"{c}: {top}", (cx, cy), fontsize=8, ha="center",
                    bbox=dict(boxstyle="round,pad=0.2", fc="white", alpha=0.8))
    ax.set_title(f"UMAP with {k} KMeans clusters (label = dominant topic)")
    ax.set_xticks([]); ax.set_yticks([])
    fig.savefig(OUT / "embedding_clusters.png", dpi=140, bbox_inches="tight")
    plt.close(fig)

    # Coverage: corpus share vs eval-target share, per topic (program level).
    prog_topic = {p: topic_of(p + "/") for p in set(programs)}
    corpus_progs = Counter(prog_topic.values())
    corpus_chunks = Counter(topics)
    tgt = [t for t in eval_targets() if t in prog_topic]
    tgt_progs = set(tgt)
    tgt_topic = Counter(prog_topic[p] for p in tgt_progs)

    rows = []
    for n in names:
        rows.append({
            "topic": n,
            "programs": corpus_progs[n],
            "chunks": int(corpus_chunks[n]),
            "programs_targeted_by_eval": tgt_topic[n],
            "program_coverage": round(tgt_topic[n] / corpus_progs[n], 3),
        })
    rows.sort(key=lambda r: r["program_coverage"])

    fig, ax = plt.subplots(figsize=(10, 5.5))
    y = np.arange(len(rows))
    ax.barh(y, [r["programs"] for r in rows], color="#cfd8dc", label="programs in corpus")
    ax.barh(y, [r["programs_targeted_by_eval"] for r in rows], color="#c8691e", label="targeted by an eval question")
    ax.set_yticks(y); ax.set_yticklabels([r["topic"] for r in rows])
    for i, r in enumerate(rows):
        ax.text(r["programs"] + 0.5, i, f'{r["program_coverage"]:.0%}', va="center", fontsize=9)
    ax.set_xlabel("programs")
    ax.set_title("Eval coverage by topic area (percent = share of programs targeted)")
    ax.legend(loc="lower right")
    fig.tight_layout()
    fig.savefig(OUT / "eval_coverage.png", dpi=140, bbox_inches="tight")
    plt.close(fig)

    # Programs never targeted, plus nearest-neighbour outliers (isolated in embedding space).
    untargeted = sorted(p for p in prog_topic if p not in tgt_progs)
    cent = {p: X[[i for i, q in enumerate(programs) if q == p]].mean(axis=0) for p in prog_topic}
    pn = list(cent)
    C = np.array([cent[p] / np.linalg.norm(cent[p]) for p in pn])
    sim = C @ C.T
    np.fill_diagonal(sim, -1)
    nn = sim.max(axis=1)
    isolated = [(pn[i], round(float(nn[i]), 3)) for i in np.argsort(nn)[:12]]

    summary = {
        "chunks": int(len(X)),
        "programs": len(prog_topic),
        "pca_explained_variance_2pc": round(float(pca.explained_variance_ratio_.sum()), 3),
        "topics": rows,
        "programs_targeted": len(tgt_progs),
        "untargeted_programs_by_topic": {
            n: [p for p in untargeted if prog_topic[p] == n] for n in names
        },
        "most_isolated_programs": isolated,
    }
    (OUT / "coverage_summary.json").write_text(json.dumps(summary, indent=2))

    print(f"PCA 2-PC variance: {pca.explained_variance_ratio_.sum():.1%}")
    print(f"{len(tgt_progs)} of {len(prog_topic)} programs are eval targets\n")
    for r in rows:
        print(f'{r["topic"]:34s} programs={r["programs"]:3d} chunks={r["chunks"]:4d} '
              f'targeted={r["programs_targeted_by_eval"]:2d} ({r["program_coverage"]:.0%})')
    print("\nMost isolated programs (lowest nearest-neighbour similarity):")
    for p, s in isolated:
        print(f"  {s}  {p}")


if __name__ == "__main__":
    main()
