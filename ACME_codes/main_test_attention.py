from allele_seq import *
from pseudo_seq import *
from protein_scanning import *
from scoring import *
from foutput import *
from keras.models import model_from_json
from read_proteome import *
from allele_list import *
import numpy as np
from read_attentions import * 
import scipy.stats as ss
import copy

def main_test_attention(global_args):
    #Read the alleles and their pseudo-sequences
    [blosum_matrix, aa, main_dir, output_path] = global_args
    path_train = main_dir+ "binding_data/binding_data.txt"
    path_seq = main_dir+ "HLA_A_B.txt"
    seq_dict = allele_seq(path_seq)
    pseq_dict = pseudo_seq(seq_dict, global_args)

    #Load the models trained previously
    models = []
    for i in range(25):
        json_f = open(main_dir + "models/model_"+str(i)+".json", 'r')
        loaded_model_json = json_f.read()
        json_f.close()
        loaded_model = model_from_json(loaded_model_json)
        loaded_model.load_weights((main_dir + "models/model_"+str(i)+".h5"))
        models.append(loaded_model)  
    
    #Randomly sample peptides from the proteome
    proteome_path = main_dir + "Homo_sapiens.GRCh38.pep.all.fa"
    proteome = read_proteome(proteome_path)    
    peptides = protein_scanning(proteome, global_args)
    
    #Start to output the motifs 
    #Output is a dictionary
    foutput("heatmap_dict = {\n", output_path)
    alleles = allele_list(path_train)
    D1 = []
    D2 = []
    for allele in alleles:       
        #First select 1000 peptides with the highest (or lowest, depending on which mode you choose) binding affinities.
        if allele not in pseq_dict.keys():
            continue
        pseqs = [pseq_dict[allele] for i in range(len(peptides))]
        #Predict the binding affinities of the peptides.
        scores = scoring(models, [np.array(peptides), np.array(pseqs)])    
        #Select the ones with the highest/lowest affinities.
        upper_threshold = sorted(scores)[-1000]
        positives = [i for i in range(len(scores)) if scores[i] > upper_threshold]
        selected_peptides = [peptides[j] for j in positives]
        #Record the predicted affinities before masking
        Ao = [scores[k] for k in positives]
        #Pseudo-sequences of the corresponding peptide    .
        positive_pseqs = [pseqs[j] for j in positives]
        #copy the peptides so that we could mask certain positions and make predictions later
        pep_mask_highest = copy.deepcopy(selected_peptides)
        pep_mask_lowest = copy.deepcopy(selected_peptides)
        #Use the model to assign attention scores to the residues in each peptide.
        attentions_of_models = []
        model_inputs =[np.array(selected_peptides), np.array(positive_pseqs)]
        #We have an ensembl of models. Use each of them to assign attention scores.
        #The attention scores given by different models are averaged to get the final attention score .
        for model in models:
            attentions = get_attentions(model, model_inputs, print_shape_only=False, layer_name=None)
            attentions_of_models.append(attentions)
        heatmap = np.zeros((20,9))
        for i, pep in enumerate(selected_peptides):
            #Take the mean(average) of the attention given by different models
            pep_attention = [np.mean(residue_attentions) for residue_attentions \
                            in list(zip(*[attentions_of_models[model_index][i] for model_index in range(len(models))]))]
            #In the encoded matrix, each residue correspond to 2 rows. The attention scores of these
            #2 positions are summed to get the attention of this residue.
            pep_attention = [(pep_attention[k] + pep_attention[k + 12 +3]) for k in range(9)]
            #Using zeros to mask the positions with the highest attention value
            pep_mask_highest[i][np.argmax(pep_attention)] = np.zeros(20)
            pep_mask_highest[i][np.argmax(pep_attention) + 12 + 3] = np.zeros(20)
            #Using zeros to mask the positions with the lowest attention value
            pep_mask_lowest[i][np.argmin(pep_attention)] = np.zeros(20)
            pep_mask_lowest[i][np.argmin(pep_attention) + 12 + 3] = np.zeros(20)
        Amh = scoring(models, [np.array(pep_mask_highest), np.array(pseqs)])
        Aml = scoring(models, [np.array(pep_mask_lowest), np.array(pseqs)])
        new_D1 = abs(np.subtract(Amh, Ao))
        new_D2 = abs(np.subtract(Aml, Ao))
        D1.extend(new_D1)
        D2.extend(new_D2)
        foutput(allele + " " + str(np.median(new_D1)) + " " + str(np.median(new_D2))\
                + " " + str(ss.kruskal(new_D1, new_D2)), output_path)
    foutput("mean D1 is "+str(np.median(D1)), output_path)
    foutput("mean D2 is "+str(np.median(D2)), output_path)
    foutput("Mann-Whitney U test "+str(ss.kruskal(D1, D2)), output_path)
                