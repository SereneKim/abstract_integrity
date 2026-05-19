#!/usr/bin/env python3
import gc
from pathlib import Path

import polars as pl
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq

# -------------------- Paths --------------------
NOVELTY_DIR = Path("/rhea/scratch/brussel/vo/000/bvo00042/science_of_science/NoveltyChallenge/")
OPENALEX_DIR = Path("/rhea/scratch/brussel/vo/000/bvo00042/science_of_science/OpenAlex/")

ABSTRACTS_PATH = NOVELTY_DIR / "OpenAlex_Abstracts_Clean_11343567.parquet"
NOVELTY_META_PATH = NOVELTY_DIR / "novelty_challenge_metadata.csv"

META_PATH = OPENALEX_DIR / (
    "OpenAlex_2025_11_11_id_id_raw_doi_title_publication_date_type_has_abstract_"
    "primary_topic_name_subfield_name_field_name_domain_name_open_access_is_oa_"
    "is_retracted_language_created_date_ALL_DATES_full_v5.parquet"
)

CITATIONS_PATH = OPENALEX_DIR / (
    "OpenAlex_2025_11_11_id_id_raw_cited_by_count_referenced_works_count_created_date_"
    "ALL_DATES_full_v5.parquet"
)

# Output now contains 2M ids and both titles
OUT_PATH = NOVELTY_DIR / "OpenAlex_random_sample_2M_with_titlemeta_titleabs_abstract.parquet"
OUT_TMP = OUT_PATH.with_suffix(".parquet.tmp")

# Temp intermediates (in NoveltyChallenge folder for fast scratch I/O)
META_SUBSET_PATH = NOVELTY_DIR / "tmp_sample_2M_metadata_subset.parquet"
META_SUBSET_TMP = META_SUBSET_PATH.with_suffix(".parquet.tmp")

ABS_MATCH_PATH = NOVELTY_DIR / "tmp_sample_2M_abstracts_matches.parquet"
ABS_MATCH_TMP = ABS_MATCH_PATH.with_suffix(".parquet.tmp")

# -------------------- Sampling params --------------------
N_SAMPLE = 2_000_000
SEED = 20260120
OVERSAMPLE_FACTOR = 1.30
INV_U64_PLUS1 = 1.0 / 18446744073709551616.0  # 1 / 2^64

# Batch sizes (tune down if needed)
BATCH_ABS = 50_000
BATCH_META = 150_000

# ID regex sanity check (as requested)
ID_PATTERN = r"^https://openalex\.org/W\d+$"


def print_row_count_lazy(lf: pl.LazyFrame, label: str) -> int:
    n = lf.select(pl.len().alias("n_rows")).collect(engine="streaming").item()
    print(f"{label}: rows = {int(n):,}", flush=True)
    return int(n)


def print_metadata_total_rows() -> None:
    n = (
        pl.scan_parquet(str(META_PATH))
        .select(pl.len().alias("n"))
        .collect(engine="streaming")
        .item()
    )
    print(f"[Meta] Total rows in metadata parquet: {int(n):,}", flush=True)


def abstracts_id_sanity_check() -> None:
    """
    Memory-efficient check over abstracts parquet:
    - total rows (including duplicates)
    - valid ids count using the provided regex
    - null ids count
    """
    pf = pq.ParquetFile(str(ABSTRACTS_PATH))
    total_rows = 0
    valid_rows = 0
    null_rows = 0

    for batch in pf.iter_batches(batch_size=250_000, columns=["id"], use_threads=True):
        arr = batch.column(0)
        n = batch.num_rows
        total_rows += n

        # nulls
        nn = pc.is_null(arr)
        null_rows += int(pc.sum(pc.cast(nn, pa.int64())).as_py())

        # valid ids (regex) on non-null
        # fill null -> False to avoid null-propagation in sums
        m = pc.match_substring_regex(arr, ID_PATTERN)
        m = pc.fill_null(m, False)
        valid_rows += int(pc.sum(pc.cast(m, pa.int64())).as_py())

    print(f"[Abstracts] Total rows (incl duplicates): {total_rows:,}", flush=True)
    print(f"[Abstracts] Valid id rows (regex):        {valid_rows:,}", flush=True)
    print(f"[Abstracts] Null id rows:                 {null_rows:,}", flush=True)


def build_step1_meta_filtered_ids() -> pl.LazyFrame:
    """
    Same filters as before (your 'current approach').
    Note: has_abstract is known imperfect, but we keep it and oversample later.
    """
    return (
        pl.scan_parquet(str(META_PATH))
        .select(["id", "publication_date", "type", "has_abstract", "is_retracted", "language"])
        .with_columns(
            pl.col("id").cast(pl.Utf8, strict=False).str.strip_chars().alias("id"),
            pl.col("publication_date").cast(pl.Utf8, strict=False).alias("publication_date"),
            pl.col("type").cast(pl.Utf8, strict=False).alias("type"),
            pl.col("language").cast(pl.Utf8, strict=False).alias("language"),
            pl.col("has_abstract").cast(pl.Boolean, strict=False).alias("has_abstract"),
            pl.col("is_retracted").cast(pl.Boolean, strict=False).alias("is_retracted"),
            pl.col("publication_date").str.slice(0, 4).cast(pl.Int32, strict=False).alias("_year"),
        )
        .filter(
            pl.col("id").is_not_null()
            & pl.col("_year").is_not_null()
            & (pl.col("_year") >= 1900)
            & (pl.col("_year") <= 2025)
            & (pl.col("type") == "article")
            & (pl.col("language") == "en")
            & (pl.col("has_abstract") == True)
            & (pl.col("is_retracted").fill_null(False) == False)
        )
        .select(["id"])
    )


def read_novelty_ids_df() -> pl.DataFrame:
    return (
        pl.read_csv(
            str(NOVELTY_META_PATH),
            columns=["OpenAlexID (as URL)"],
            schema_overrides={"OpenAlexID (as URL)": pl.Utf8},
        )
        .rename({"OpenAlexID (as URL)": "id"})
        .with_columns(pl.col("id").cast(pl.Utf8, strict=False).str.strip_chars())
        .filter(pl.col("id").is_not_null())
        .unique(subset=["id"])
    )


def build_cited_ids_lazy() -> pl.LazyFrame:
    # ids are unique in this parquet (per your assumption)
    return (
        pl.scan_parquet(str(CITATIONS_PATH))
        .select(["id", "cited_by_count"])
        .with_columns(
            pl.col("id").cast(pl.Utf8, strict=False).str.strip_chars().alias("id"),
            pl.col("cited_by_count").cast(pl.Int64, strict=False).alias("cited_by_count"),
        )
        .filter(pl.col("id").is_not_null() & (pl.col("cited_by_count").fill_null(0) >= 1))
        .select(["id"])
    )


def sample_2m_ids(lf_ids: pl.LazyFrame, n_population_rows_est: int) -> pl.DataFrame:
    p = min(1.0, (N_SAMPLE * OVERSAMPLE_FACTOR) / max(1, n_population_rows_est))

    for attempt in range(1, 10):
        lf_cand = (
            lf_ids
            .with_columns(
                (pl.col("id").hash(seed=SEED).cast(pl.UInt64).cast(pl.Float64) * pl.lit(INV_U64_PLUS1)).alias("_u")
            )
            .filter(pl.col("_u") < p)
            .sort("_u")
            .limit(N_SAMPLE)
            .select(["id"])
        )
        df_sample = lf_cand.collect(engine="streaming")

        if df_sample.height >= N_SAMPLE:
            if df_sample.height > N_SAMPLE:
                df_sample = df_sample.head(N_SAMPLE)
            print(f"Step 4: sampled ids = {df_sample.height:,} (p={p:.6g}, attempt={attempt})", flush=True)
            return df_sample

        p = min(1.0, p * 1.7)

    raise RuntimeError(f"Failed to obtain {N_SAMPLE:,} ids after retries.")


def write_metadata_subset_chunked(sample_ids_df: pl.DataFrame) -> int:
    """
    Extract metadata rows for the sampled ids (2M) in batches (PyArrow), and write a compact parquet.
    Includes all sampling columns + created_date + updated_date + title_metadata.
    """
    ids_list = sample_ids_df["id"].to_list()
    value_set = pa.array(ids_list, type=pa.string())
    lookup_opts = pc.SetLookupOptions(value_set=value_set)

    pf = pq.ParquetFile(str(META_PATH))

    # columns we want from metadata
    cols = [
        "id",
        "title",            # will be renamed to title_metadata
        "publication_date",
        "type",
        "language",
        "has_abstract",
        "is_retracted",
        "created_date",
        "updated_date",
    ]
    cols_use = [c for c in cols if c in pf.schema.names]
    if "id" not in cols_use:
        raise RuntimeError("Metadata parquet missing id column.")

    META_SUBSET_TMP.unlink(missing_ok=True)
    writer = None
    total_written = 0

    for batch in pf.iter_batches(batch_size=BATCH_META, columns=cols_use, use_threads=True):
        tbl = pa.Table.from_batches([batch])

        # normalize id trim
        id_idx = tbl.schema.get_field_index("id")
        tbl = tbl.set_column(id_idx, "id", pc.utf8_trim_whitespace(tbl["id"]))

        mask = pc.is_in(tbl["id"], options=lookup_opts)
        tbl_f = tbl.filter(mask)

        if tbl_f.num_rows == 0:
            continue

        # rename metadata title -> title_metadata
        names = tbl_f.schema.names
        new_names = ["title_metadata" if n == "title" else n for n in names]
        tbl_f = tbl_f.rename_columns(new_names)

        if writer is None:
            writer = pq.ParquetWriter(str(META_SUBSET_TMP), tbl_f.schema, compression="zstd")
        writer.write_table(tbl_f)
        total_written += tbl_f.num_rows

    if writer is not None:
        writer.close()
    else:
        # empty file with expected schema
        schema = pa.schema(
            [
                pa.field("id", pa.string()),
                pa.field("title_metadata", pa.string()),
                pa.field("publication_date", pa.string()),
                pa.field("type", pa.string()),
                pa.field("language", pa.string()),
                pa.field("has_abstract", pa.bool_()),
                pa.field("is_retracted", pa.bool_()),
                pa.field("created_date", pa.string()),
                pa.field("updated_date", pa.date32()),
            ]
        )
        empty = pa.Table.from_arrays([pa.array([], type=f.type) for f in schema], schema=schema)
        pq.write_table(empty, str(META_SUBSET_TMP), compression="zstd")

    META_SUBSET_TMP.replace(META_SUBSET_PATH)

    # cleanup
    del ids_list, value_set, lookup_opts, pf
    gc.collect()

    return int(total_written)


def write_abstracts_matches_chunked(sample_ids_df: pl.DataFrame) -> int:
    """
    Extract matching rows (id,title,abstract) from the big abstracts parquet for sampled ids (2M).
    Writes ONLY matches (so can be <2M).
    """
    ids_list = sample_ids_df["id"].to_list()
    value_set = pa.array(ids_list, type=pa.string())
    lookup_opts = pc.SetLookupOptions(value_set=value_set)

    pf = pq.ParquetFile(str(ABSTRACTS_PATH))

    cols = ["id", "title", "abstract"]
    cols_use = [c for c in cols if c in pf.schema.names]
    if "id" not in cols_use:
        raise RuntimeError("Abstracts parquet missing id column.")

    ABS_MATCH_TMP.unlink(missing_ok=True)
    writer = None
    total_written = 0

    for batch in pf.iter_batches(batch_size=BATCH_ABS, columns=cols_use, use_threads=True):
        tbl = pa.Table.from_batches([batch])

        # normalize id trim
        id_idx = tbl.schema.get_field_index("id")
        tbl = tbl.set_column(id_idx, "id", pc.utf8_trim_whitespace(tbl["id"]))

        mask = pc.is_in(tbl["id"], options=lookup_opts)
        tbl_f = tbl.filter(mask)

        if tbl_f.num_rows == 0:
            continue

        if writer is None:
            writer = pq.ParquetWriter(str(ABS_MATCH_TMP), tbl_f.schema, compression="zstd")
        writer.write_table(tbl_f)
        total_written += tbl_f.num_rows

    if writer is not None:
        writer.close()
    else:
        schema = pa.schema([("id", pa.string()), ("title", pa.string()), ("abstract", pa.string())])
        empty = pa.Table.from_arrays(
            [pa.array([], pa.string()), pa.array([], pa.string()), pa.array([], pa.string())],
            schema=schema,
        )
        pq.write_table(empty, str(ABS_MATCH_TMP), compression="zstd")

    ABS_MATCH_TMP.replace(ABS_MATCH_PATH)

    # cleanup
    del ids_list, value_set, lookup_opts, pf
    gc.collect()

    return int(total_written)


def main() -> None:
    print("python:", __import__("sys").version.split()[0], flush=True)
    print("polars:", pl.__version__, flush=True)
    print("Output will be written to:", OUT_PATH, flush=True)

    # ---- Quick comparison row count (metadata total) ----
    print_metadata_total_rows()

    # ---- Abstracts parquet sanity check (memory efficient) ----
    abstracts_id_sanity_check()

    # ---------------- Step 1 ----------------
    lf_step1 = build_step1_meta_filtered_ids()
    _ = print_row_count_lazy(lf_step1, "Step 1 (after metadata filters)")

    # ---------------- Step 2 ----------------
    novelty_ids_df = read_novelty_ids_df()
    lf_step2 = lf_step1.join(novelty_ids_df.lazy(), on="id", how="anti")
    _ = print_row_count_lazy(lf_step2, "Step 2 (after removing novelty challenge ids)")

    del lf_step1, novelty_ids_df
    gc.collect()

    # ---------------- Step 3 ----------------
    lf_cited_ids = build_cited_ids_lazy()
    lf_step3_ids = lf_step2.join(lf_cited_ids, on="id", how="semi").select(["id"])
    n3 = print_row_count_lazy(lf_step3_ids, "Step 3 (after keeping cited_by_count>=1)")

    del lf_step2, lf_cited_ids
    gc.collect()

    if n3 < N_SAMPLE:
        raise RuntimeError(f"Not enough rows after filtering: {n3:,} < {N_SAMPLE:,}")

    # ---------------- Step 4 (sample 2M) ----------------
    df_sample_ids = sample_2m_ids(lf_step3_ids, n_population_rows_est=n3)
    del lf_step3_ids
    gc.collect()

    # ---------------- Step 4b: extract metadata subset for sampled ids ----------------
    print("Extracting metadata subset for sampled ids (chunked)...", flush=True)
    meta_written = write_metadata_subset_chunked(df_sample_ids)
    print(f"Metadata subset rows written: {meta_written:,} (expected {N_SAMPLE:,})", flush=True)

    # ---------------- Step 5: extract abstracts matches (chunked) ----------------
    print("Extracting abstracts matches for sampled ids (chunked)...", flush=True)
    abs_written = write_abstracts_matches_chunked(df_sample_ids)
    print(f"Abstracts matches rows written (may include duplicates): {abs_written:,}", flush=True)

    # ---- How many sampled ids could not be matched to abstracts? ----
    # Use ids only (cheap)
    n_missing_abs = (
        df_sample_ids.lazy()
        .join(pl.scan_parquet(str(ABS_MATCH_PATH)).select(["id"]), on="id", how="anti")
        .select(pl.len().alias("n_missing"))
        .collect(engine="streaming")
        .item()
    )
    print(f"IDs NOT matched to abstracts parquet: {int(n_missing_abs):,}", flush=True)

    # ---------------- Final output build (LEFT JOIN; keep ALL 2M ids) ----------------
    # Base = metadata subset (has title_metadata + filter columns + dates)
    # Left-join abstracts matches to add title + abstract; unmatched -> nulls as requested
    print("Building final output (streaming sink_parquet)...", flush=True)

    lf_meta = pl.scan_parquet(str(META_SUBSET_PATH))
    lf_abs = pl.scan_parquet(str(ABS_MATCH_PATH)).select(["id", "title", "abstract"])

    # IMPORTANT: validate right side uniqueness (catch duplicates instead of exploding rows)
    # If this errors due to duplicates, we can deduplicate ABS_MATCH_PATH by id in a follow-up step.
    lf_out = (
        lf_meta.join(lf_abs, on="id", how="left", validate="m:1")
        .select(
            [
                "id",
                "title_metadata",
                "title",       # from abstracts parquet
                "abstract",    # from abstracts parquet
                "publication_date",
                "type",
                "language",
                "has_abstract",
                "is_retracted",
                "created_date",
                "updated_date",
            ]
        )
    )

    OUT_TMP.unlink(missing_ok=True)
    lf_out.sink_parquet(str(OUT_TMP), compression="zstd")
    OUT_TMP.replace(OUT_PATH)

    # output row count check
    n_out = (
        pl.scan_parquet(str(OUT_PATH))
        .select(pl.len().alias("n"))
        .collect(engine="streaming")
        .item()
    )
    print(f"Output parquet rows: {int(n_out):,} (expected {N_SAMPLE:,})", flush=True)

    # cleanup
    del df_sample_ids
    gc.collect()

    print("DONE.", flush=True)


if __name__ == "__main__":
    main()
