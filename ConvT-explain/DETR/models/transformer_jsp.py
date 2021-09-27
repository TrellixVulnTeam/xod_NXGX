# Copyright (c) Facebook, Inc. and its affiliates. All Rights Reserved
"""
DETR Transformer class.

Copy-paste from torch.nn.Transformer with modifications:
    * positional encodings are passed in MHattention
    * extra LN at the end of encoder is removed
    * decoder returns a stack of activations from all decoding layers

app of jsp

2021-09-27 : add off_decoder_head

"""


import copy
from typing import Optional, List

import torch
import torch.nn.functional as F
from torch import nn, Tensor
from DETR.modules.layers import *
from DETR.modules.layers import MultiheadAttention


class Transformer(nn.Module):

    def __init__(self, d_model=512, nhead=8, num_encoder_layers=6,
                 num_decoder_layers=6, dim_feedforward=2048, dropout=0.1,
                 activation="relu", normalize_before=False,
                 return_intermediate_dec=False, off_decoder_head=False):
        super().__init__()

        encoder_layer = TransformerEncoderLayer(d_model, nhead, dim_feedforward,
                                                dropout, activation, normalize_before)
        encoder_norm = LayerNorm(d_model) if normalize_before else None
        self.encoder = TransformerEncoder(encoder_layer, num_encoder_layers, encoder_norm)
    
        decoder_layer = TransformerDecoderLayer(d_model, nhead, dim_feedforward,
                                                dropout, activation, normalize_before, off_decoder_head=off_decoder_head)#추가-0927 : add decoder head
        decoder_norm = LayerNorm(d_model)
        self.decoder = TransformerDecoder(decoder_layer, num_decoder_layers, decoder_norm,
                                          return_intermediate=return_intermediate_dec)

        self._reset_parameters()

        self.d_model = d_model
        self.nhead = nhead
        
       
        self.clone = Clone()
        
        

    def _reset_parameters(self):
        for p in self.parameters():
            if p.dim() > 1:
                nn.init.xavier_uniform_(p)

    def forward(self, src, mask, query_embed, pos_embed):
        
        # flatten NxCxHxW to HWxNxC
        print('#In Transformer.forward. input : src, mask')
        print('shape of src : ', src.shape)
        print('shape of mask : ', mask.shape)
        
        bs, c, h, w = src.shape
        self.src_shape = src.shape
        src = src.flatten(2).permute(2, 0, 1)
        self.src_flat_shape = src.shape
        pos_embed = pos_embed.flatten(2).permute(2, 0, 1)
        query_embed = query_embed.unsqueeze(1).repeat(1, bs, 1)
        mask = mask.flatten(1)
        
   
        tgt = torch.zeros_like(query_embed)
        print('Start Transformer.forward.encoder')
        print('Input : src, mask, pos_embed')
        
        
        
        print('shape of src :', src.shape)
        print('shape of mask :', mask.shape)
        print('shape of pos_embed :', pos_embed.shape)
              
        memory = self.encoder(src, src_key_padding_mask=mask, pos=pos_embed)
        print('End Transformer.forward.encoder. output : memory -> ', memory.shape)
        mem1, mem2 = self.clone(memory, 2)
        print('Start Transformer.forward.decoder')
        print('Input : tgt, mem1, mask, pos_embed, query_embed...')
        print('shape of tgt :', tgt.shape)
        print('shape of mem1 :', mem1.shape)
        print('shape of mask :', mask.shape)
        hs = self.decoder(tgt, mem1, memory_key_padding_mask=mask,
                          pos=pos_embed, query_pos=query_embed)
        print('End Transformer.forward.decoder. output : hs -> ', hs.shape)
        
        print('#Out Transformer.forward. output: hs.transpose(1,2), mem2.permute(1,2,0).view(src.shape)\n->',
              hs.transpose(1,2).shape, mem2.permute(1,2,0).view(bs,c,h,w).shape)
        return hs.transpose(1, 2), mem2.permute(1, 2, 0).view(bs, c, h, w)

    def relprop(self, cam, alpha, **kwargs):
        print('# In Transformer.relprop(cam, alpha)')
        print(""",cam_hs = cam[0].transpose(1, 2)
        cam_mem1 = cam[1].view(self.src_flat_shape[1], self.src_flat_shape[2], self.src_flat_shape[0])
        cam_mem1 = cam_mem1.permute(2, 0, 1)

        cam_tgt, cam_mem2 = self.decoder.relprop(cam_hs, alpha, **kwargs)
        cam_memory = self.clone.relprop([cam_mem1, cam_mem2], alpha, **kwargs)

        cam_src = self.encoder.relprop(cam_memory, alpha, **kwargs)
        cam_src = cam_src.permute(1, 2, 0).reshape(*self.src_shape)
        """)
        cam_hs = cam[0].transpose(1, 2)
        print('shape of cam_hs : ', cam_hs.shape)
        cam_mem1 = cam[1].view(self.src_flat_shape[1], self.src_flat_shape[2], self.src_flat_shape[0])
        print('shape of cam_mem1 : ', cam_mem1.shape)
        cam_mem1 = cam_mem1.permute(2, 0, 1)
        print('shape of cam_mem1 : ', cam_mem1.shape)
        
        print('#- Start transformer.decoder.relprop(cam_hs, alpha)')
        cam_tgt, cam_mem2 = self.decoder.relprop(cam_hs, alpha, **kwargs)
        
        print('shape of cam_tgt : ', cam_tgt.shape)
        print('shape of cam_mem2 : ', cam_mem2.shape)
        
        print('#- Start transformer.clone.relprop([cam_mem1, cam_mem2], alpha')
        cam_memory = self.clone.relprop([cam_mem1, cam_mem2], alpha, **kwargs)
        print('shape of cam_memory : ', cam_memory.shape)
        print('#- Start transformer.encoder.relprop(cam_memory, alpha)')
        cam_src = self.encoder.relprop(cam_memory, alpha, **kwargs)
        print('shape of cam_src : ', cam_src.shape)
        cam_src = cam_src.permute(1, 2, 0).reshape(*self.src_shape)
        print('shape of cam_src : ', cam_src.shape)
        
        print('# Out Transformer.relprop. output : cam_src\nshape of cam_src : ', cam_src.shape)
        
        return cam_src

class TransformerEncoder(nn.Module):

    def __init__(self, encoder_layer, num_layers, norm=None):
        super().__init__()
        self.layers = _get_clones(encoder_layer, num_layers)
        self.num_layers = num_layers
        self.norm = norm

    def forward(self, src,
                mask: Optional[Tensor] = None,
                src_key_padding_mask: Optional[Tensor] = None,
                pos: Optional[Tensor] = None):
        output = src

        for layer in self.layers:
            output = layer(output, src_mask=mask,
                           src_key_padding_mask=src_key_padding_mask, pos=pos)

        if self.norm is not None:
            output = self.norm(output)

        return output

    def relprop(self, cam, alpha, **kwargs):
        if self.norm is not None:
            cam = self.norm.relprop(cam, alpha, **kwargs)

        for layer in self.layers[::-1]:
            cam = layer.relprop(cam, alpha, **kwargs)

        return cam


class TransformerDecoder(nn.Module):

    def __init__(self, decoder_layer, num_layers, norm=None, return_intermediate=False):
        super().__init__()
        self.layers = _get_clones(decoder_layer, num_layers)
        self.num_layers = num_layers
        # self.norm_list = norm
        # self.clone_list = _get_clones(Clone, num_layers-1)
        self.clone_list = [Clone() for _ in range(num_layers-1)]
        self.norm = norm
        self.return_intermediate = return_intermediate
        self.clone = Clone()
    def forward(self, tgt, memory,
                tgt_mask: Optional[Tensor] = None,
                memory_mask: Optional[Tensor] = None,
                tgt_key_padding_mask: Optional[Tensor] = None,
                memory_key_padding_mask: Optional[Tensor] = None,
                pos: Optional[Tensor] = None,
                query_pos: Optional[Tensor] = None):
        output = tgt
        print('In Transformer.decoder.forward(tgt, memory...). shape of output(tgt) :', output.shape)
        intermediate = []

        mem_list = self.clone(memory, len(self.layers))

        for i, layer in enumerate(self.layers):
            output = layer(output, mem_list[i], tgt_mask=tgt_mask,
                           memory_mask=memory_mask,
                           tgt_key_padding_mask=tgt_key_padding_mask,
                           memory_key_padding_mask=memory_key_padding_mask,
                           pos=pos, query_pos=query_pos)
            if self.return_intermediate:
                if i == self.num_layers - 1:
                    intermediate.append(self.norm(output))
                else:
                    output, output_norm = self.clone_list[i](output, 2)
                    intermediate.append(self.norm(output_norm))

        if self.norm is not None:
            if not self.return_intermediate:
                output = self.norm(output)
            # output = self.norm(output)
            # if self.return_intermediate:
            #     intermediate.pop()
            #     intermediate.append(output)
        
        if self.return_intermediate:
            return torch.stack(intermediate)
        print('End Transformer.decoder.forward(tgt, memory...). shape of output :', output.shape)
        return output.unsqueeze(0)
        
    def relprop(self, cam_list, alpha, **kwargs):
        # FIXME
        if self.return_intermediate:
            # cam = cam[-1]
            pass
        else:
            cam_list = cam_list.squeeze(0)

        if self.norm is not None:
            if not self.return_intermediate:
                cam_list = self.norm.relprop(cam_list, alpha, **kwargs)

        cam_mem_list = []
        for i, layer in enumerate(self.layers[::-1]):
            j = self.num_layers - i - 1

            if self.return_intermediate:
                if j == self.num_layers - 1:
                    cam = self.norm.relprop(cam_list[j], alpha, **kwargs)
                else:
                    cam_norm = self.norm.relprop(cam_list[j], alpha, **kwargs)
                    cam = self.clone_list[j].relprop([cam, cam_norm], alpha, **kwargs)
            else:
                cam = cam_list

            # cam_mem_i == encoder
            # cam == targets in decoder
            cam, cam_mem_i = layer.relprop(cam, alpha, **kwargs)

            cam_mem_list += [cam_mem_i]

        cam_mem = self.clone.relprop(cam_mem_list, alpha, **kwargs)

        return cam, cam_mem


class TransformerEncoderLayer(nn.Module):

    def __init__(self, d_model, nhead, dim_feedforward=2048, dropout=0.1,
                 activation="relu", normalize_before=False):
        super().__init__()
        self.self_attn = MultiheadAttention(d_model, nhead, dropout=dropout)
        # Implementation of Feedforward model
        self.linear1 = Linear(d_model, dim_feedforward)
        self.dropout = Dropout(dropout)
        self.linear2 = Linear(dim_feedforward, d_model)

        self.norm1 = LayerNorm(d_model)
        self.norm2 = LayerNorm(d_model)
        self.dropout1 = Dropout(dropout)
        self.dropout2 = Dropout(dropout)

        self.activation = _get_activation_fn(activation)
        self.normalize_before = normalize_before

        self.add1 = Add()
        self.add2 = Add()
        self.clone1 = Clone()
        self.clone2 = Clone()
        self.clone3 = Clone()
        self.clone4 = Clone()

        self.wembd1 = WithPosEmbd()

    def forward_post(self,
                     src,
                     src_mask: Optional[Tensor] = None,
                     src_key_padding_mask: Optional[Tensor] = None,
                     pos: Optional[Tensor] = None):
        src_1, src_2, src_3 = self.clone1(src, 3)
        webmd = self.wembd1(src_1, pos)
        q, k = self.clone2(webmd, 2)
        src2 = self.self_attn(q, k, value=src_2, attn_mask=src_mask,
                              key_padding_mask=src_key_padding_mask)#[0]
        # src2_1, src2_2 = self.clone3(src2, 2)
        src_drop = self.dropout1(src2)
        src = self.add1([src_3, src_drop])
        src = self.norm1(src)

        src_1, src_2 = self.clone3(src, 2)

        src_1 = self.linear1(src_1)
        src_1 = self.activation(src_1)
        src_1 = self.dropout(src_1)
        src2 = self.linear2(src_1)
        src2 = self.dropout2(src2)
        src = self.add2([src_2, src2])
        src = self.norm2(src)
        return src

    def forward_post_relprop(self, cam_src, alpha, **kwargs):
        cam_src = self.norm2.relprop(cam_src, alpha, **kwargs)
        cam_src_2, cam_src2 = self.add2.relprop(cam_src, alpha, **kwargs)
        cam_src2 = self.dropout2.relprop(cam_src2, alpha, **kwargs)
        cam_src_1 = self.linear2.relprop(cam_src2, alpha, **kwargs)
        cam_src_1 = self.dropout.relprop(cam_src_1, alpha, **kwargs)
        cam_src_1 = self.activation.relprop(cam_src_1, alpha, **kwargs)
        cam_src_1 = self.linear1.relprop(cam_src_1, alpha, **kwargs)

        cam_src = self.clone3.relprop([cam_src_1, cam_src_2], alpha, **kwargs)

        cam_src = self.norm1.relprop(cam_src, alpha, **kwargs)
        cam_src_3, cam_src_drop = self.add1.relprop(cam_src, alpha, **kwargs)
        cam_src2 = self.dropout1.relprop(cam_src_drop, alpha, **kwargs)
        cam_q, cam_k, cam_src_2 = self.self_attn.relprop(cam_src2, alpha, **kwargs)
        cam_webd = self.clone2.relprop([cam_q, cam_k], alpha, **kwargs)
        cam_src_1 = self.wembd1.relprop(cam_webd, alpha, **kwargs)
        cam_src = self.clone1.relprop([cam_src_1, cam_src_2, cam_src_3], alpha, **kwargs)

        return cam_src

    # def forward_pre(self, src,
    #                 src_mask: Optional[Tensor] = None,
    #                 src_key_padding_mask: Optional[Tensor] = None,
    #                 pos: Optional[Tensor] = None):
    #     src_1, src_2 = self.clone1(src, 2)
    #     src2 = self.norm1(src_1)
    #     src2_1, src2_2 = self.clone2(src2, 2)
    #     webmd = self.wembd1(src2_1, pos)
    #     q, k = self.clone3(webmd, 2)
    #     src2 = self.self_attn(q, k, value=src2_2, attn_mask=src_mask,
    #                           key_padding_mask=src_key_padding_mask)#[0]
    #     src_drop = self.dropout1(src2)
    #     src = self.add1([src_2, src_drop])
    #     src_1, src_2 = self.clone4(src, 2)
    #
    #     src2 = self.norm2(src_1)
    #     src2 = self.linear1(src2)
    #     src2 = self.activation(src2)
    #     src2 = self.dropout(src2)
    #     src2 = self.linear2(src2)
    #     src2 = self.dropout2(src2)
    #     src = self.add2([src_2, src2])
    #     return src
    #
    # def forward_pre_relprop(self, cam_src, alpha, **kwargs):
    #     cam_src_2, cam_src2 = self.add2.relprop(cam_src, alpha, **kwargs)
    #     cam_src2 = self.dropout2.relprop(cam_src2, alpha, **kwargs)
    #     cam_src2 = self.linear2.relprop(cam_src2, alpha, **kwargs)
    #     cam_src2 = self.dropout.relprop(cam_src2, alpha, **kwargs)
    #     cam_src2 = self.activation.relprop(cam_src2, alpha, **kwargs)
    #     cam_src2 = self.linear1.relprop(cam_src2, alpha, **kwargs)
    #     cam_src_1 = self.norm2.relprop(cam_src2, alpha, **kwargs)
    #
    #     cam_src = self.clone4.relprop([cam_src_1, cam_src_2], alpha, **kwargs)
    #     cam_src_2, cam_src_drop = self.add1.relprop(cam_src, alpha, **kwargs)
    #     cam_src2 = self.dropout1.relprop(cam_src_drop, alpha, **kwargs)
    #     cam_q, cam_k, cam_src2_2 = self.self_attn.relprop(cam_src2, alpha, **kwargs)
    #     cam_webd = self.clone3.relprop([cam_q, cam_k], alpha, **kwargs)
    #     cam_src2_1 = self.wembd1.relprop(cam_webd, alpha, **kwargs)
    #     cam_src2 = self.clone2.relprop([cam_src2_1, cam_src2_2], alpha, **kwargs)
    #     cam_src_1 = self.norm1.relprop(cam_src2, alpha, **kwargs)
    #     cam_src = self.clone1.relprop([cam_src_1, cam_src_2], alpha, **kwargs)
    #
    #     return cam_src

    def forward(self, src,
                src_mask: Optional[Tensor] = None,
                src_key_padding_mask: Optional[Tensor] = None,
                pos: Optional[Tensor] = None):
        if self.normalize_before:
            return self.forward_pre(src, src_mask, src_key_padding_mask, pos)
        return self.forward_post(src, src_mask, src_key_padding_mask, pos)

    def relprop(self, cam, alpha, **kwargs):
        if self.normalize_before:
            return self.forward_pre_relprop(cam, alpha, **kwargs)
        return self.forward_post_relprop(cam, alpha, **kwargs)



class TransformerDecoderLayer(nn.Module):

    def __init__(self, d_model, nhead, dim_feedforward=2048, dropout=0.1,
                 activation="relu", normalize_before=False, off_decoder_head=False): #추가:0927-off_decoder_head : Off.
        super().__init__()
        self.self_attn = MultiheadAttention(d_model, nhead, dropout=dropout)
        self.multihead_attn = MultiheadAttention(d_model, nhead, dropout=dropout, no_weight = off_decoder_head)#추가:0927-off_decoder_head : Off.
        # Implementation of Feedforward model
        self.linear1 = Linear(d_model, dim_feedforward)
        self.dropout = Dropout(dropout)
        self.linear2 = Linear(dim_feedforward, d_model)

        self.norm1 = LayerNorm(d_model)
        self.norm2 = LayerNorm(d_model)
        self.norm3 = LayerNorm(d_model)
        self.dropout1 = Dropout(dropout)
        self.dropout2 = Dropout(dropout)
        self.dropout3 = Dropout(dropout)

        self.activation = _get_activation_fn(activation)
        self.normalize_before = normalize_before

        self.add1 = Add()
        self.add2 = Add()
        self.add3 = Add()
        self.clone1 = Clone()
        self.clone2 = Clone()
        self.clone3 = Clone()
        self.clone4 = Clone()
        self.clone5 = Clone()

        self.wembd1 = WithPosEmbd()
        self.wembd2 = WithPosEmbd()
        self.wembd3 = WithPosEmbd()

    def forward_post(self, tgt, memory,
                     tgt_mask: Optional[Tensor] = None,
                     memory_mask: Optional[Tensor] = None,
                     tgt_key_padding_mask: Optional[Tensor] = None,
                     memory_key_padding_mask: Optional[Tensor] = None,
                     pos: Optional[Tensor] = None,
                     query_pos: Optional[Tensor] = None):
        tgt_1, tgt_2, tgt_3 = self.clone1(tgt, 3)
        webmd = self.wembd1(tgt_1, query_pos)
        q, k = self.clone2(webmd, 2)
        tgt2 = self.self_attn(q, k, value=tgt_2, attn_mask=tgt_mask,
                              key_padding_mask=tgt_key_padding_mask)#[0]
        tgt_drop = self.dropout1(tgt2)
        tgt = self.add1([tgt_3, tgt_drop])
        tgt = self.norm1(tgt)
        tgt_1, tgt_2 = self.clone3(tgt, 2)

        mem_1, mem_2 = self.clone4(memory, 2)
        q = self.wembd2(tgt_1, query_pos)
        k = self.wembd3(mem_1, pos)
        print('Transformer.decoder.forward(_post). k and value : k, mem_2', k.shape, mem_2.shape)
        tgt2 = self.multihead_attn(query=q,
                                   key=k,
                                   value=mem_2,
                                   attn_mask=memory_mask,
                                   key_padding_mask=memory_key_padding_mask)#[0]
        tgt_drop = self.dropout2(tgt2)
        tgt = self.add2([tgt_2, tgt_drop])
        tgt = self.norm2(tgt)
        tgt_1, tgt_2 = self.clone5(tgt, 2)
        tgt2 = self.linear1(tgt_1)
        tgt2 = self.activation(tgt2)
        tgt2 = self.dropout(tgt2)
        tgt2 = self.linear2(tgt2)
        tgt2 = self.dropout3(tgt2)
        tgt = self.add3([tgt_2, tgt2])
        tgt = self.norm3(tgt)
        return tgt

    def forward_post_relprop(self, cam_tgt, alpha, **kwargs):
        cam_tgt = self.norm3.relprop(cam_tgt, alpha, **kwargs)
        cam_tgt_2, cam_tgt2 = self.add3.relprop(cam_tgt, alpha, **kwargs)
        cam_tgt2 = self.dropout3.relprop(cam_tgt2, alpha, **kwargs)
        cam_tgt2 = self.linear2.relprop(cam_tgt2, alpha, **kwargs)
        cam_tgt2 = self.dropout.relprop(cam_tgt2, alpha, **kwargs)
        cam_tgt2 = self.activation.relprop(cam_tgt2, alpha, **kwargs)
        cam_tgt_1 = self.linear1.relprop(cam_tgt2, alpha, **kwargs)
        cam_tgt = self.clone5.relprop([cam_tgt_1, cam_tgt_2], alpha, **kwargs)
        cam_tgt = self.norm2.relprop(cam_tgt, alpha, **kwargs)
        cam_tgt_2, cam_tgt_drop = self.add2.relprop(cam_tgt, alpha, **kwargs)
        cam_tgt2 = self.dropout2.relprop(cam_tgt_drop, alpha, **kwargs)
        cam_q, cam_k, cam_mem_2 = self.multihead_attn.relprop(cam_tgt2, alpha, **kwargs)
        cam_mem_1 = self.wembd3.relprop(cam_k, alpha, **kwargs)
        cam_tgt_1 = self.wembd2.relprop(cam_q, alpha, **kwargs)
        cam_mem = self.clone4.relprop([cam_mem_1, cam_mem_2], alpha, **kwargs)

        cam_tgt = self.clone3.relprop([cam_tgt_1, cam_tgt_2], alpha, **kwargs)
        cam_tgt = self.norm1.relprop(cam_tgt, alpha, **kwargs)
        cam_tgt_3, cam_tgt_drop = self.add1.relprop(cam_tgt, alpha, **kwargs)
        cam_tgt2 = self.dropout1.relprop(cam_tgt_drop, alpha, **kwargs)
        cam_q, cam_k, cam_tgt_2 = self.self_attn.relprop(cam_tgt2, alpha, **kwargs)
        cam_webmd = self.clone2.relprop([cam_q, cam_k], alpha, **kwargs)
        cam_tgt_1 = self.wembd1.relprop(cam_webmd, alpha, **kwargs)
        # cam_tgt = self.clone1.relprop([cam_tgt_1, cam_tgt_2, cam_tgt_3], alpha, **kwargs)
        cam_tgt = sum([cam_tgt_1, cam_tgt_2, cam_tgt_3])

        return cam_tgt, cam_mem

    def forward_pre(self, tgt, memory,
                    tgt_mask: Optional[Tensor] = None,
                    memory_mask: Optional[Tensor] = None,
                    tgt_key_padding_mask: Optional[Tensor] = None,
                    memory_key_padding_mask: Optional[Tensor] = None,
                    pos: Optional[Tensor] = None,
                    query_pos: Optional[Tensor] = None):
        tgt_1, tgt_2 = self.clone1(tgt, 2)
        tgt2 = self.norm1(tgt_1)
        webmd = self.wembd1(tgt2, query_pos)
        q, k = self.clone2(webmd, 2)
        tgt2 = self.self_attn(q, k, value=tgt2, attn_mask=tgt_mask,
                              key_padding_mask=tgt_key_padding_mask)#[0]
        tgt_drop = self.dropout1(tgt2)
        tgt = self.add1([tgt_2, tgt_drop])
        tgt_1, tgt_2 = self.clone3(tgt, 2)
        tgt2 = self.norm2(tgt_1)

        mem_1, mem_2 = self.clone4(memory, 2)
        q = self.wembd2(tgt2, query_pos)
        k = self.wembd3(mem_1, pos)
        tgt2 = self.multihead_attn(query=q,
                                   key=k,
                                   value=mem_2, attn_mask=memory_mask,
                                   key_padding_mask=memory_key_padding_mask)#[0]
        tgt_drop = self.dropout2(tgt2)
        tgt = self.add2([tgt_2, tgt_drop])
        tgt_1, tgt_2 = self.clone5(tgt, 2)
        tgt2 = self.norm3(tgt_1)
        tgt2 = self.linear1(tgt2)
        tgt2 = self.activation(tgt2)
        tgt2 = self.dropout(tgt2)
        tgt2 = self.linear2(tgt2)
        tgt2 = self.dropout3(tgt2)
        tgt = self.add3([tgt_2, tgt2])
        return tgt

    def forward_pre_relprop(self, cam_tgt, alpha, **kwargs):
        cam_tgt_2, cam_tgt2 = self.add3.relprop(cam_tgt, alpha, **kwargs)
        cam_tgt2 = self.dropout3.relprop(cam_tgt2, alpha, **kwargs)
        cam_tgt2 = self.linear2.relprop(cam_tgt2, alpha, **kwargs)
        cam_tgt2 = self.activation.relprop(cam_tgt2, alpha, **kwargs)
        cam_tgt2 = self.linear1.relprop(cam_tgt2, alpha, **kwargs)
        cam_tgt_1 = self.norm3.relprop(cam_tgt2, alpha, **kwargs)
        cam_tgt = self.clone5.relprop([cam_tgt_1, cam_tgt_2], alpha, **kwargs)
        cam_tgt_2, cam_tgt_drop = self.add2.relprop(cam_tgt, alpha, **kwargs)
        cam_tgt2 = self.dropout2.relprop(cam_tgt_drop, alpha, **kwargs)
        cam_q, cam_k, cam_mem_2 = self.multihead_attn.relprop(cam_tgt2, alpha, **kwargs)
        cam_mem_1 = self.wembd3.relprop(cam_k, alpha, **kwargs)
        cam_tgt2 = self.wembd2.relprop(cam_q, alpha, **kwargs)
        cam_mem = self.clone4.relprop([cam_mem_1, cam_mem_2], alpha, **kwargs)

        cam_tgt_1 = self.norm2.relprop(cam_tgt2, alpha, **kwargs)
        cam_tgt = self.clone3.relprop([cam_tgt_1, cam_tgt_2], alpha, **kwargs)
        cam_tgt_2, cam_tgt_drop = self.add1.relprop(cam_tgt, alpha, **kwargs)
        cam_tgt2 = self.dropout1.relprop(cam_tgt_drop, alpha, **kwargs)
        cam_q, cam_k, cam_tgt2 = self.self_attn.relprop(cam_tgt2, alpha, **kwargs)
        cam_webmd = self.clone2.relprop([cam_q, cam_k], alpha, **kwargs)
        cam_tgt2 = self.wembd1.relprop(cam_webmd, alpha, **kwargs)
        cam_tgt_1 = self.norm1.relprop(cam_tgt2, alpha, **kwargs)
        cam_tgt = self.clone2.relprop([cam_tgt_1, cam_tgt_2], alpha, **kwargs)

        return cam_tgt, cam_mem

    def forward(self, tgt, memory,
                tgt_mask: Optional[Tensor] = None,
                memory_mask: Optional[Tensor] = None,
                tgt_key_padding_mask: Optional[Tensor] = None,
                memory_key_padding_mask: Optional[Tensor] = None,
                pos: Optional[Tensor] = None,
                query_pos: Optional[Tensor] = None):
        if self.normalize_before:
            return self.forward_pre(tgt, memory, tgt_mask, memory_mask,
                                    tgt_key_padding_mask, memory_key_padding_mask, pos, query_pos)
        return self.forward_post(tgt, memory, tgt_mask, memory_mask,
                                 tgt_key_padding_mask, memory_key_padding_mask, pos, query_pos)

    def relprop(self, cam, alpha, **kwargs):
        if self.normalize_before:
            return self.forward_pre_relprop(cam, alpha, **kwargs)
        return self.forward_post_relprop(cam, alpha, **kwargs)



def _get_clones(module, N):
    return nn.ModuleList([copy.deepcopy(module) for i in range(N)])


def build_transformer_jsp(args):
    return Transformer(
        d_model=args.hidden_dim,
        dropout=args.dropout,
        nhead=args.nheads,
        dim_feedforward=args.dim_feedforward,
        num_encoder_layers=args.enc_layers,
        num_decoder_layers=args.dec_layers,
        normalize_before=args.pre_norm,
        return_intermediate_dec=True,
        off_decoder_head= args.off_decoder_head #수정(1) : Out heads(input : [layers x heads ] matrix) 
    )


def _get_activation_fn(activation):
    """Return an activation function given a string"""
    if activation == "relu":
        return ReLU()
    if activation == "gelu":
        return GELU()
    # if activation == "glu":
    #     return F.glu
    raise RuntimeError(F"activation should be relu/gelu, not {activation}.")
