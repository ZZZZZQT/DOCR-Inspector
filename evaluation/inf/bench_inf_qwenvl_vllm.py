from transformers import AutoProcessor
from PIL import Image
from vllm import LLM, SamplingParams
import glob
import os
import json
import torch
from qwen_vl_utils import process_vision_info
from tqdm import tqdm
import re
import sys
import argparse

Image.MAX_IMAGE_PIXELS = None

def process_input(image_path, prompt, llm, processor):
    try:
        contents = [
            {
                "type": "image", 
                "image": Image.open(image_path).convert('RGB'),
                "min_pixels": 224 * 224, 
                "max_pixels": 1280 * 28 * 28,
            }
        ]
        messages = [{
                "role": "user",
                "content": [
                    *contents,
                    {"type": "text", "text": prompt},
                ],
            }]
        
        prompt = processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        img_data, _ = process_vision_info(messages)
        
        return {
            "prompt": prompt,
            "multi_modal_data": {"image": img_data},
        }
    except Exception as e:
        print(f"Error processing image {image_path}: {str(e)}")
        return None

def inference(image_paths, prompts, llm, processor):
    # 设置采样参数
    sampling_params = SamplingParams(temperature=0.0, max_tokens=4096)
    inputs = []

    for path, prompt in tqdm(zip(image_paths, prompts), desc="Processing Images"):
        processed_input = process_input(path, prompt, llm, processor)
        if processed_input is not None:
            inputs.append(processed_input)

    # 进行推理
    outputs = llm.generate(inputs, sampling_params=sampling_params)

    results  = [ o.outputs[0].text if o.outputs else "" for o in outputs]
    return results

def answer_format(results):
    try:
        # think = re.findall(r'<think>(.*?)</think>', results, re.DOTALL)
        answer = re.findall(r'<answer>(.*?)</answer>', results, re.DOTALL)
        error_type_list = re.findall(r'<error_type>(.*?)</error_type>', results, re.DOTALL)
        get_first = lambda l: l[0] if l else ""
        return {
            "output": results,
            # "think": get_first(think),
            "answer": get_first(answer),
            "error_type_list": error_type_list
        }
    except Exception as e:
        return {
            "output": results,
            # "think": "",
            "answer": "",
            "error_type_list": ""
        }

def main(model_name, model_path, prompt_type): 
    print("Initializing processor and model... (This may take a while)")
    try:
        processor = AutoProcessor.from_pretrained(model_path, trust_remote_code=True)
        llm = LLM(
            model=model_path,
            tensor_parallel_size=4,
            gpu_memory_utilization=0.8,
            # max_num_seqs=20,
            max_model_len=32768,
            trust_remote_code=True,
        )
        print("Model and processor initialized successfully.")
    except Exception as e:
        print(f"Failed to initialize model: {str(e)}")
        sys.exit(1)

    
    with open(f"./utils/Prompt_{args.prompt_type}_think.txt", "r") as f:
        PROMPT = f.read()

    with open("./DOCRcaseBench/benchmark_v1.json", "r", encoding="utf-8") as f:
        data = json.load(f)
        
    image_root = "./DOCRcaseBench/image"
    save_root = "./results"

    final_data = []
    image_paths = []
    prompts = []

    for item in data:
        image_paths.append(os.path.join(image_root, item["crop_image"]))
        prompt_text = f"<image>\n{PROMPT}\n{item['pred']}"
        prompts.append(prompt_text)
        

    results = inference(image_paths, prompts, llm, processor)

    for result, item in zip(results, data):
        formatted_result = answer_format(result)
        item["output"] = formatted_result
        final_data.append(item)

    print(f"Processed {len(final_data)} items")

    output_file = os.path.join(save_root, f"Qwen25-VL-7B-{prompt_type}CoT_test_results.json")
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(final_data, f, ensure_ascii=False, indent=4)
        
    print(f"Completed processing for model: Qwen25-VL-7B-{prompt_type}CoT")
    print(f"Results saved to: {output_file}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--model_name", type=str, default="Qwen2.5-VL-7B-Instruct")
    parser.add_argument("--model_path", type=str, default="Qwen/Qwen2.5-VL-7B-Instruct")
    parser.add_argument("--prompt_type", type=str, default="wo")
    
    args = parser.parse_args()
    model_name = args.model_name
    model_path = args.model_path
    prompt_type = args.prompt_type

    main(model_name, model_path, prompt_type)

