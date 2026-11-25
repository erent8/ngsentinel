---
title: NGSentinel
emoji: 🧬
colorFrom: blue
colorTo: indigo
sdk: docker
app_port: 7860
pinned: false
license: mit
short_description: NGS quality control with explainable PASS/REVIEW/FAIL
---

# NGSentinel — NGS Quality Control & Genomic Analysis Platform

Upload FASTQ files (single- or paired-end, .fastq / .fastq.gz) or use the synthetic demo dataset.
NGSentinel validates the input, runs FastQC, preprocesses the reads with fastp, re-assesses quality,
aggregates the results with MultiQC and decides **PASS / REVIEW / FAIL** with configurable, explained rules.
Every run ends in a self-contained HTML report with full provenance.

This public instance runs in a shared, temporary environment:
uploads are limited to 150 MB per file and analyses are deleted after 24 hours.
Do not upload confidential or human-identifiable data.
Research and education tool — not for clinical diagnosis.
