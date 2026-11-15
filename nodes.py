"""
AXIRIS · H3 Image Soft Start

MiniMax H3 Image is built to edit from pictures. With text alone it renders hard (burnt contrast, an HDR look).
Showing it an empty (black) picture during the first sampling steps puts it back on its own ground: a softer,
more photographic render, with as much detail.

The idea comes from Kijai (ComfyUI-KJNodes, "text with empty image"). This code is written from scratch; it
contains no line of KJNodes.

How it works, and why not just the core nodes:
  · the black picture is encoded ALONE, with an empty prompt ("Picture 1: "): its tokens do not depend on the prompt;
  · they are put IN FRONT of the text conditioning, encoded on its own: the text never "sees" the picture
    (plugging a picture into the core node encodes the prompt after the picture: a different image);
  · H3's token tags ("minimax_token_tags": 0 = image, 1 = text) are joined in the same order
    (the core ConditioningConcat keeps only the first part's tags: the count would no longer match);
  · on [start, end] of the steps: picture + text; outside: text alone.
No VAE: the picture is not a reference to edit, it only conditions the text encoder.

Two nodes:
  · AXIRIS · H3 Image Soft Start — a drop-in replacement for "MiniMax H3 Image Conditioning":
    same inputs, same outputs. It CALLS the core node; with text alone it adds the empty picture.
    With real reference pictures (an edit), it is the core node, unchanged.
  · AXIRIS · H3 Image — empty picture (first steps) — the same thing as a separate node, to put between the
    core conditioning (without pictures) and the KSampler.
"""
import torch


class AxirisH3ImageVide:
    CATEGORY = "AXIRIS/H3"
    RETURN_TYPES = ("CONDITIONING",)
    RETURN_NAMES = ("positive",)
    FUNCTION = "appliquer"
    DESCRIPTION = ("H3 Image, text only: an empty picture during the first steps, for a softer render. "
                   "Goes between \"MiniMax H3 Image Conditioning\" (without pictures) and the KSampler.")

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "clip": ("CLIP", {"tooltip": "The same text encoder as the prompt conditioning"}),
            "conditioning": ("CONDITIONING", {"tooltip": "The positive of \"MiniMax H3 Image Conditioning\", without pictures"}),
            "debut": ("FLOAT", {"default": 0.0, "min": 0.0, "max": 1.0, "step": 0.01, "tooltip": "Start of the steps with the empty picture"}),
            "fin": ("FLOAT", {"default": 0.25, "min": 0.0, "max": 1.0, "step": 0.01, "tooltip": "End of the steps with the empty picture — 0.25 = the first 2 of 6 steps"}),
            "taille": ("INT", {"default": 512, "min": 64, "max": 2048, "step": 32, "tooltip": "Side of the black picture, in pixels"}),
        }}

    def appliquer(self, clip, conditioning, debut, fin, taille):
        if fin <= debut:
            return (conditioning,)
        noire = torch.zeros(1, taille, taille, 3)
        jetons_image, extras_image = clip.encode_from_tokens_scheduled(
            clip.tokenize("", images=[noire], picture_label="Picture %d: "))[0]
        sortie = []
        for jetons, extras in conditioning:
            etiq = extras.get("minimax_token_tags")
            avec = dict(extras)
            if etiq is not None and extras_image.get("minimax_token_tags") is not None:
                avec["minimax_token_tags"] = torch.cat([extras_image["minimax_token_tags"].to(etiq.device), etiq])
            avec["start_percent"], avec["end_percent"] = debut, fin
            sortie.append([torch.cat([jetons_image.to(jetons.device, jetons.dtype), jetons], dim=1), avec])
            if debut > 0.0:
                sortie.append([jetons, {**extras, "start_percent": 0.0, "end_percent": debut}])
            if fin < 1.0:
                sortie.append([jetons, {**extras, "start_percent": fin, "end_percent": 1.0}])
        return (sortie,)


class AxirisH3ImageSoftStart:
    CATEGORY = "AXIRIS/H3"
    RETURN_TYPES = ("CONDITIONING", "LATENT")
    RETURN_NAMES = ("positive", "LATENT")
    FUNCTION = "conditionner"
    DESCRIPTION = ("Replaces \"MiniMax H3 Image Conditioning\". Text only: an empty picture during the first steps — "
                   "a softer, more photographic render. With pictures: the core node, unchanged.")

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "clip": ("CLIP",),
            "prompt": ("STRING", {"multiline": True, "dynamicPrompts": True}),
            "width": ("INT", {"default": 0, "min": 0, "max": 16384, "step": 32, "tooltip": "0 = as the core node"}),
            "height": ("INT", {"default": 0, "min": 0, "max": 16384, "step": 32}),
            "image_vide": ("BOOLEAN", {"default": True, "tooltip": "Text only: the empty picture during the first steps"}),
            "debut": ("FLOAT", {"default": 0.0, "min": 0.0, "max": 1.0, "step": 0.01}),
            "fin": ("FLOAT", {"default": 0.25, "min": 0.0, "max": 1.0, "step": 0.01, "tooltip": "0.25 = the first 2 of 6 steps"}),
            "taille": ("INT", {"default": 512, "min": 64, "max": 2048, "step": 32}),
        }, "optional": {
            "vae": ("VAE",),
            "image_1": ("IMAGE", {"tooltip": "The picture to edit (<Picture 1>)"}),
            "image_2": ("IMAGE",), "image_3": ("IMAGE",), "image_4": ("IMAGE",),
        }}

    def conditionner(self, clip, prompt, width, height, image_vide, debut, fin, taille, vae=None, **images):
        from comfy_extras.nodes_minimax_h3 import MiniMaxH3ImageConditioning
        images = {k: v for k, v in images.items() if v is not None} or None
        cond, latent = MiniMaxH3ImageConditioning.execute(clip, prompt, width, height, vae=vae, images=images).result
        if image_vide and not images:
            cond = AxirisH3ImageVide().appliquer(clip, cond, debut, fin, taille)[0]
        return (cond, latent)


NODE_CLASS_MAPPINGS = {"AxirisH3ImageVide": AxirisH3ImageVide, "AxirisH3ImageSoftStart": AxirisH3ImageSoftStart}
NODE_DISPLAY_NAME_MAPPINGS = {"AxirisH3ImageVide": "✦ AXIRIS · H3 Image — image vide (premiers pas)",
                              "AxirisH3ImageSoftStart": "✦ AXIRIS · H3 Image Soft Start"}
