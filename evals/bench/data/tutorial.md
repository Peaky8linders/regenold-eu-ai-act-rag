# Scripts Navigation Guide
Reference and workflow for the scripts folder

This guide walks you through the key scripts for downloading, processing, and quantising AI models and datasets. Use the commands below to navigate and execute each step efficiently.

---

## 1. Download the AI Act & Extract Articles
Purpose: Create the folder structure and dataset for the AI Act.

Steps:
- Navigate to the scripts directory:
  ```bash
  $ cd scripts/
  ```
- Run the script to set up the folder structure:
  ```bash
  $ python make_ai_act.py
  ```
- The automatic download is deprecated. After running the script, manually download the AI Act PDF from [this link](https://eur-lex.europa.eu/legal-content/EN/TXT/PDF/?uri=OJ:L_202401689) and save it as `ai_act.pdf` in the `data/datasets/ai_act/` folder.
- Re-run the script to process the downloaded file:
  ```bash
  $ python make_ai_act.py
  ```

---

## 2. LLM Model Download & Quantisation

Download and quantise the open-source `gpt-oss-120b` model for efficient GPU usage.
Model Used: [gpt-oss-120b](https://huggingface.co/openai/gpt-oss-120b) (Apache-2.0 licence)

Steps:
1. Use the Hugging Face CLI to download the model to a local directory:
    ```bash
    $ hf download https://huggingface.co/openai/gpt-oss-120b --cache_dir=<local_path>
    ```
2. Use the llama.cpp project to convert the model. Follow their [hardware-specific instructions](https://github.com/ggml-org/llama.cpp) for building the bins.
    ```bash
    $ python llama.cpp/convert_hf_to_gguf.py <local_path>/models--openai--gpt-oss-120b/snapshots/b5c939de8f754692c1647ca79fbf85e8c1e70f8a --outtype f16 --outfile gpt_oss_120b.gguf
    ```
3. Quantise the model for reduced GPU memory usage:
    ```bash
    $ llama.cpp/build/bin/llama-quantize gpt_oss_120b.gguf gpt_oss_120b_mxfp4.gguf MXFP4_MOE
    ```
4. (Optional) Link model and bin to scripts for easier access
    ```bash
    $ ln -s <custom-path>/gpt_oss_120b_mxfp4.gguf .
    $ ln -s llama.cpp/build/bin/llama-run .
    ```
---

## 3. Scenario Generation

1. Check/validate that config file `scenario_gen.yml` has correct path of `llama-run` and model path.

    Example:

    ```yaml
    run_path: ./                                                             
    model_path: ./cache/gpt_oss_120b_mxfp4.gguf
    ```

2. Run respective python script. Scenarios can be generated for four levels according to the AI Act (prohibited, high-risk, limited, minimal)
    ```bash
    $ python generate_scenarios.py config/scenario_gen.yml [prohibited/high-risk/limited/minimal/all]
    ```
    Depending on the GPU capacity flag `all` might not work as intended, individual running is required.

3. (Optional) Clean high-risk scenarios. There are runs that might produce the Article reference in the end of the `intended_use` field after a semicolon. To remove that the following script can be run:
    ```bash
    $ python mkdata/clean_hr.py <hr.json> <new_hr.json>
    ```

---

## 4. Related Articles Generation
1. Check/validate that config file `relarts_gen.yml` has correct path of `llama-run` and model path.

    Example:

    ```yaml
    run_path: ./                                                             
    model_path: ./cache/gpt_oss_120b_mxfp4.gguf
    ```

2. Run respective python script as follows.

    Template:
    ```bash
    $ python generate_relarts.py config/relarts_gen.yml '{json_from_previous_run}'
    ```
    Example:
    ```bash
    $ python generate_relarts.py config/relarts_gen.yml '{"role": "Provider", "intended_use": "AI safety component for autonomous surgical robots that monitors instrument positioning and triggers emergency stop", "system_type": "Real‑time safety monitoring AI for medical robots", "input_data": "Live video feed, force‑torque sensor data, patient vital signs", "domain": "Product safety AI systems"}
    ```

3. (Optional) Make incremental json by adding the related articles field.
    ```bash
    $ python ccheck_relarts.py <gen_scen.json> <dir_of_txts_generated_from_rel_arts_runs>/
    ```

---

## 5. Obligation Generation
1. Check/validate that config file `oblg_gen.yml` has correct path of `llama-run` and model path.

    Example:

    ```yaml
    run_path: ./                                                             
    model_path: ./cache/gpt_oss_120b_mxfp4.gguf
    ```

2. Run respective python script as follows.

    Template:
    ```bash
    $ python generate_obligations.py config/relarts_gen.yml '{json_from_previous_run_incremental}' ai_act_articles.pkl
    ```
    Example:
    ```bash
    $ python generate_obligations.py config/oblg_gen.yml '{"role": "Provider", "intended_use": "AI safety component for autonomous surgical robots that monitors instrument positioning and triggers emergency stop", "system_type": "Real‑time safety monitoring AI for medical robots", "input_data": "Live video feed, force‑torque sensor data, patient vital signs", "domain": "Product safety AI systems", "related_articles": [6, 8, 9, 10, 13, 14, 15, 16, 17, 18, 19, 20, 21, 43, 44, 47, 48, 49, 72, 73]}' data/datasets/ai_act/ai_act_articles.pkl
    ```

3. (Optional) Make incremental json by adding the obligations field.
    ```bash
    $ python ccheck_oblg.py <rel_arts.json> <dir_of_txts_generated_from_oblg_runs>/
    ```

---

## 6. Generate QA pairs
1. Check/validate that config file `qa.yml` has correct path of `llama-run` and model path.

    Example:

    ```yaml
    run_path: ./                                                             
    model_path: ./cache/gpt_oss_120b_mxfp4.gguf
    ```

2. Run respective python script as follows.
    ```bash
    $ python generate_qa.py config/qa.yml
    ```
---

## Notes
- The llama.cpp build process is hardware-dependent. Refer to their documentation for detailed instructions.
- The gpt-oss-120b model is released under the Apache-2.0 licence.