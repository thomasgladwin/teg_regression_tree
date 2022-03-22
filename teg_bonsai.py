import numpy as np
import scipy
from scipy import stats

# numpy.seterr(all='raise')

#
# Decision tree: Regression
#

class Tree():

    def __init__(self, X, y, maxDepth, alpha0, peek_ahead_max_depth=0, split_val_quantiles = [], peek_ahead_quantiles = [], nSamples = 0, internal_cross_val=0, beta0_vec = [0, 0]):
        self.X = X
        self.y = y
        self.maxDepth = maxDepth
        self.alpha0 = alpha0
        self.peek_ahead_max_depth = peek_ahead_max_depth
        self.split_val_quantiles = split_val_quantiles
        self.peek_ahead_quantiles = peek_ahead_quantiles
        self.nSamples = nSamples
        self.internal_cross_val = internal_cross_val
        self.beta0_vec = beta0_vec
        self.peek_ahead_depth = 0 # Changed in loop in build_tree
        self.tree_info = []

    def build_tree(self):
        tree0 = []
        cost_complexity_criterion = np.inf
        best_peek_crit = np.NaN
        best_raw_tree = []
        best_C_min_v_crossval = []
        best_C_min_v_null = []
        p = 1
        for peek_ahead_depth in range(self.peek_ahead_max_depth + 1):
            print('Finding tree for peek_ahead_depth = ', peek_ahead_depth)
            self.peek_ahead_depth = peek_ahead_depth
            tree0_this, cost_complexity_criterion_this, raw_tree, C_min_v_crossval, C_min_v_null, p = self.teg_regression_tree()
            print('Cost-Complexity Criterion = ', cost_complexity_criterion_this)
            if cost_complexity_criterion_this < cost_complexity_criterion:
                tree0 = tree0_this
                cost_complexity_criterion = cost_complexity_criterion_this
                best_peek_crit = peek_ahead_depth
                best_raw_tree = raw_tree
                best_C_min_v_crossval = C_min_v_crossval
                best_C_min_v_null = C_min_v_null
                print(" ! New best tree !")
            print("\n")
        print("Best tree was found at peek-ahead depth = ", best_peek_crit)
        Output = {'tree': tree0, 'cost_complexity_criterion':cost_complexity_criterion, 'best_peek_crit':best_peek_crit, 'raw_tree':best_raw_tree, 'CV_distr':best_C_min_v_crossval, 'null_distr':best_C_min_v_null, 'p':p}
        self.tree_info = Output
        return Output

    def teg_regression_tree(self):
        if (self.nSamples == 0):
            if self.internal_cross_val == 0:
                print('Internal cross validation not used with nSamples=0.')
            mean_y = np.nanmean(self.y)
            sd_y = np.sqrt(np.var(self.y))
            y = (self.y - mean_y) / sd_y
            tree0 = self.teg_tree_inner(self.X, y)
            C, nodes_collapsed = self.prune_the_tree(tree0)
            C_min_v_crossval = []
            C_min_v_null = []
            p = 1
        else:
            best_mean_y = np.NaN
            best_sd_y = np.NaN
            best_C_min = np.inf
            best_tree = []
            best_C = []
            best_nodes_collapsed = []
            C_min_v_crossval = []
            C_min_v_null = []
            for iSample in range(self.nSamples):
                #print(iSample)
                # Random split sample into:
                #   Subsample to construct tree
                #   Independent subsample used for entropy per terminal node
                # Additionally, create a randomly permuted sample to generate a null distribution over the samples
                perm_indices = np.random.permutation(len(self.y))
                a = int(np.floor(len(self.y) / 2))
                set1_indices = perm_indices[1:a]
                set2_indices = perm_indices[a:]
                y_1 = self.y[set1_indices]
                X_1 = self.X[set1_indices, :]
                y_2 = self.y[set2_indices]
                X_2 = self.X[set2_indices, :]
                mean_y_1 = np.nanmean(y_1)
                sd_y_1 = np.sqrt(np.var(y_1))
                y_1 = (y_1 - mean_y_1) / sd_y_1
                mean_y_2 = np.nanmean(y_2)
                sd_y_2 = np.sqrt(np.var(y_2))
                y_2 = (y_2 - mean_y_2) / sd_y_2
                # Null distribution
                y_null = np.random.permutation(y_2) # Already normalized
                X_null = X_2.copy()
                #
                tree0 = self.teg_tree_inner(X_1, y_1)
                C, nodes_collapsed = self.prune_the_tree(tree0)
                tree0_CV = self.tree_copy(tree0, X_2, y_2)
                #print(tree0_CV)
                C_CV, nodes_collapsed_CV = self.prune_the_tree(tree0_CV)
                tree0_null = self.tree_copy(tree0, X_null, y_null)
                C_null, nodes_collapsed_null = self.prune_the_tree(tree0_null)
                #
                C_min_v_crossval.append(np.min(C_CV))
                C_min_v_null.append(np.min(C_null))
                if self.internal_cross_val == 1:
                    best_C_min_to_use = np.min(C_CV)
                else:
                    best_C_min_to_use = np.min(C)
                # Pick the tree that has the lowest minimal CCC found in the C vector
                if best_C_min_to_use < best_C_min:
                    best_C_min = best_C_min_to_use
                    best_mean_y = mean_y_1
                    best_sd_y = sd_y_1
                    best_tree = tree0
                    best_C = C
                    best_nodes_collapsed = nodes_collapsed
            mean_y = best_mean_y
            sd_y = best_sd_y
            tree0 = best_tree
            C = best_C
            nodes_collapsed = best_nodes_collapsed
            d_for_NHST = np.array(C_min_v_crossval) - np.array(C_min_v_null)
            p = scipy.stats.ttest_1samp(d_for_NHST, 0)

        #print(tree0)
        #print(C)
        #print(nodes_collapsed)
        # print(len(C))
        self.print_tree(tree0, C, nodes_collapsed, mean_y, sd_y)
        collapsed_tree = self.collapse_tree(tree0, C, nodes_collapsed, mean_y, sd_y)
        if len(C) > 0:
            return collapsed_tree, min(C), tree0, C_min_v_crossval, C_min_v_null, p
        else:
            return collapsed_tree, np.NaN, tree0, C_min_v_crossval, C_min_v_null, p

    def teg_tree_inner(self, X, y, iDepth=0, node_index_v = [0], prev_terminal_node_pred=np.nan):
        # print("Params: ", twostep, internalEnsemble)
        if (iDepth == 0):
            node_index_v[0] = 0
        else:
            node_index_v[0] = node_index_v[0] + 1
        # print(node_index_v)
        if len(y) > 0:
            terminal_node_pred = np.nanmean(y)
        else:
            terminal_node_pred = 0
        SS_pre_split = self.f_SS(y)
        # Check whether maxdepth passed or y is empty
        if (iDepth >= self.maxDepth) or (len(y) <= 1) or (SS_pre_split == 0):
            if len(y) > 0:
                terminal_node_pred = np.nanmean(y)
            else:
                terminal_node_pred = prev_terminal_node_pred
            return [[np.NaN, terminal_node_pred, SS_pre_split, 0, 0, 0, node_index_v[0], iDepth, y], np.NaN, np.NaN]
        # Create branches
        # Check one step ahead
        best_split_feature = np.NaN
        best_split_val = np.NaN
        SS_best = np.inf
        for iFeature1 in range(X.shape[1]):
            best_split_val_this, SS_best_this = self.f_get_best_split_val(iFeature1, y, X, self.maxDepth - iDepth)
            if SS_best_this < SS_best:
                #print("New best!")
                best_split_feature = iFeature1
                best_split_val = best_split_val_this
                SS_best = SS_best_this
            #print("> iFeature1: ", iFeature1, ", SS_best_this: ", SS_best_this)
        if np.isnan(best_split_feature):
            if len(y) > 0:
                terminal_node_pred = np.nanmean(y)
            else:
                terminal_node_pred = prev_terminal_node_pred
            return [[np.NaN, terminal_node_pred, SS_pre_split, 0, 0, 0, node_index_v[0], iDepth, y], np.NaN, np.NaN]
        ind_left = (X[:, best_split_feature] < best_split_val)
        ind_right = (X[:, best_split_feature] >= best_split_val)
        SS_left = self.f_SS(y[ind_left])
        SS_right = self.f_SS(y[ind_right])
        best_split = [best_split_feature, best_split_val, SS_pre_split, SS_left, SS_right, len(y), node_index_v[0], iDepth, y]
        branch_left = self.teg_tree_inner(X[ind_left, :], y[ind_left], iDepth + 1, prev_terminal_node_pred=terminal_node_pred)
        branch_right = self.teg_tree_inner(X[ind_right, :], y[ind_right], iDepth + 1)
        return [best_split, branch_left, branch_right]

    def f_get_best_SS_peek(self, y, X, this_peek_ahead_depth, peek_ahead_maxDepth_limiter, current_peek_depth = 0):
        # print(current_peek_depth, peek_ahead_depth, peek_ahead_maxDepth_limiter)
        if (len(y) <= 1) or (current_peek_depth >= this_peek_ahead_depth) or (current_peek_depth >= peek_ahead_maxDepth_limiter):
            return self.f_SS_for_split(y)
        best_SS = np.inf
        best_feature_peek = np.nan
        best_val_peek = np.nan
        for iFeature_this in range(X.shape[1]):
            if len(self.peek_ahead_quantiles) == 0:
                splitting_vals_this = np.unique(X[:, iFeature_this])
            else:
                splitting_vals_this = np.quantile(X[:, iFeature_this], self.peek_ahead_quantiles)
            for val_this in splitting_vals_this:
                ind_left = (X[:, iFeature_this] < val_this)
                ind_right = (X[:, iFeature_this] >= val_this)
                best_SS_left = self.f_get_best_SS_peek(y[ind_left], X[ind_left, :], this_peek_ahead_depth, peek_ahead_maxDepth_limiter, current_peek_depth + 1)
                best_SS_right = self.f_get_best_SS_peek(y[ind_right], X[ind_right, :], this_peek_ahead_depth, peek_ahead_maxDepth_limiter, current_peek_depth + 1)
                current_SS = best_SS_left + best_SS_right
                if (current_SS < best_SS):
                    best_SS = current_SS
                    best_feature_peek = iFeature_this
                    best_val_peek = val_this
            #print(">>> best_feature_peek: ", best_feature_peek, ", best_val_peek: ", best_val_peek, ", best_SS: ", best_SS)
        return best_SS

    def f_get_best_split_val(self, iFeature1, y, X, peek_ahead_maxDepth_limiter):
        best_split_val = np.NaN
        SS_best = np.inf
        if len(self.split_val_quantiles) == 0:
            splitting_vals1 = np.unique(X[:, iFeature1])
        else:
            splitting_vals1 = np.quantile(X[:, iFeature1], split.split_val_quantiles)
        for val1 in splitting_vals1:
            ind_left = (X[:, iFeature1] < val1)
            ind_right = (X[:, iFeature1] >= val1)
            for this_peek_ahead_depth in range(self.peek_ahead_depth + 1):
                SS_left = self.f_get_best_SS_peek(y[ind_left], X[ind_left, :], this_peek_ahead_depth, peek_ahead_maxDepth_limiter)
                SS_right = self.f_get_best_SS_peek(y[ind_right], X[ind_right, :], this_peek_ahead_depth, peek_ahead_maxDepth_limiter)
                # print(iFeature1, val1, SS_left, SS_right)
                SS_this = SS_left + SS_right
                if (SS_this < SS_best):
                    SS_best = SS_this
                    best_split_val = val1
            #print(">> val1: ", val1, ", SS_this: ", SS_this)
        #print(iFeature1, best_split_val, SS_best)
        return best_split_val, SS_best

    def f_SS_for_split(self, v):
        p = len(v) / len(self.y) # Use the original, full target vector here
        if (p < self.beta0_vec[0]) and (self.beta0_vec[0] > 0):
            beta0_scaler = self.beta0_vec[1] * ((self.beta0_vec[0] - p) / self.beta0_vec[0])
        else:
            beta0_scaler = 0
        if np.isinf(beta0_scaler):
            return_val = np.inf
        else:
            return_val = self.f_SS(v) * (1 + beta0_scaler)
        return return_val

    def f_SS(self, v):
        if len(v) <= 1:
            return 0
        return_val = np.sum((v - np.mean(v))**2)
        return return_val

    # Generate tree with alternative SS_pre_split
    def tree_copy(self, tree0, X_new, y_new, iDepth=0, node_index_v = [0], previous_terminal_node_pred=np.nan):
        #print(tree0[0][0:4], node_index_v, iDepth)
        if (iDepth == 0):
            node_index_v[0] = 0
        else:
            node_index_v[0] = node_index_v[0] + 1
        # print(node_index_v)
        if len(y_new) == 0:
            terminal_node_pred = previous_terminal_node_pred
        else:
            terminal_node_pred = np.nanmean(y_new)
        SS_pre_split = self.f_SS(y_new)
        if len(y_new) == 0:
            return [[np.NaN, terminal_node_pred, SS_pre_split, 0, 0, 0, node_index_v[0], iDepth, y_new], np.NaN, np.NaN]
        if not(isinstance(tree0, list)):
            return [[np.NaN, terminal_node_pred, SS_pre_split, 0, 0, 0, node_index_v[0], iDepth, y_new], np.NaN, np.NaN]
        if np.isnan(tree0[0][0]):
            return [[np.NaN, terminal_node_pred, SS_pre_split, 0, 0, 0, node_index_v[0], iDepth, y_new], np.NaN, np.NaN]
        #print('Non-terminal node')
        best_split_feature = tree0[0][0]
        best_split_val = tree0[0][1]
        ind_left = (X_new[:, best_split_feature] < best_split_val)
        ind_right = (X_new[:, best_split_feature] >= best_split_val)
        SS_left = self.f_SS(y_new[ind_left])
        SS_right = self.f_SS(y_new[ind_right])
        best_split = [best_split_feature, best_split_val, SS_pre_split, SS_left, SS_right, len(y_new), node_index_v[0], iDepth, y_new]
        branch_left = self.tree_copy(tree0[1], X_new[ind_left, :], y_new[ind_left], iDepth + 1, previous_terminal_node_pred=terminal_node_pred)
        branch_right = self.tree_copy(tree0[2], X_new[ind_right, :], y_new[ind_right], iDepth + 1, previous_terminal_node_pred=terminal_node_pred)
        #print(branch_left[0][0], branch_right[0][0])
        return [best_split, branch_left, branch_right]

    # Cost-Complexity Pruning
    def retrieve_info_from_terminal_nodes(self, this_tree, nodes_to_collapse_tmp = [-1]):
        #print(nodes_to_collapse_tmp, this_tree[0][6], nodes_to_collapse_tmp.count(this_tree[0][6]))
        if np.isnan(this_tree[0][0]) or (nodes_to_collapse_tmp.count(this_tree[0][6]) > 0):
            # print(this_tree)
            # Elements divides by and then multiplies by Nm
            return this_tree[0][2], 1, this_tree[0][7]
        else:
            SS_left, N_left, depth_left = self.retrieve_info_from_terminal_nodes(this_tree[1], nodes_to_collapse_tmp)
            SS_right, N_right, depth_right = self.retrieve_info_from_terminal_nodes(this_tree[2], nodes_to_collapse_tmp)
            # print(N_left, N_right)
            return (SS_left + SS_right), (N_left + N_right), max(depth_left, depth_right)

    def f_C(self, this_tree, nodes_to_collapse_tmp = [-1]):
        #print('zz', nodes_to_collapse_tmp)
        if nodes_to_collapse_tmp[0] == -1:
            node_indices = []
        this_SS, this_N, max_depth_terminals = self.retrieve_info_from_terminal_nodes(this_tree, nodes_to_collapse_tmp)
        # print("fC: ", this_N, max_depth_terminals)
        return this_SS + self.alpha0 * this_N

    def get_all_node_indices(self, this_tree, node_indices = [-1]):
        if node_indices[0] == -1:
            node_indices = []
        #print(this_tree)
        node_indices.append(this_tree[0][6])
        if not(np.isnan(this_tree[0][0])):
            self.get_all_node_indices(this_tree[1], node_indices)
            self.get_all_node_indices(this_tree[2], node_indices)
        return node_indices

    def get_internal_node_indices(self, this_tree, node_indices = [-1]):
        if node_indices[0] == -1:
            node_indices = []
        #print(this_tree)
        if not(np.isnan(this_tree[0][0])):
            node_indices.append(this_tree[0][6])
            self.get_internal_node_indices(this_tree[1], node_indices)
            self.get_internal_node_indices(this_tree[2], node_indices)
        return node_indices

    def get_downstream_nodes(self, this_tree, iNode_to_collapse, downstream_nodes = [-1], downstream_on = 0):
        if len(downstream_nodes) > 0:
            if downstream_nodes[0] == -1:
                downstream_nodes = []
        if this_tree[0][6] == iNode_to_collapse:
            downstream_on = 1
        if downstream_on == 1:
            downstream_nodes.append(this_tree[0][6])
        if not(np.isnan(this_tree[0][0])):
            self.get_downstream_nodes(this_tree[1], iNode_to_collapse, downstream_nodes, downstream_on)
            self.get_downstream_nodes(this_tree[2], iNode_to_collapse, downstream_nodes, downstream_on)
        return downstream_nodes

    def prune_the_tree(self, this_tree):
        node_indices = self.get_internal_node_indices(this_tree)
        # print(node_indices)
        uncollapsed_v = [1 for a in node_indices]
        nodes_collapsed = []
        C = []
        while sum(uncollapsed_v) > 0:
            #print('uncollapsed_v: ', uncollapsed_v)
            #print('nodes_collapsed: ', nodes_collapsed[:8])
            # print('x', uncollapsed_v)
            C_vec_tmp = []
            iNode_indices_tmp = []
            #print(node_indices)
            #print(uncollapsed_v)
            for iiNode in range(len(node_indices)):
                if uncollapsed_v[iiNode] == 0:
                    continue
                iNode = node_indices[iiNode]
                iNode_indices_tmp.append(iNode)
                nodes_to_collapse_tmp = nodes_collapsed.copy()
                nodes_to_collapse_tmp.append(iNode)
                this_C = self.f_C(this_tree, nodes_to_collapse_tmp)
                C_vec_tmp.append(this_C)
            #print(iiNode_indices_tmp)
            #print(iNode_indices_tmp)
            i_C_vec_tmp = np.argmin(C_vec_tmp)
            iNode_to_collapse = iNode_indices_tmp[i_C_vec_tmp]
            #print('iNode_to_collapse: ', iNode_to_collapse, ', i_C_vec_tmp: ', i_C_vec_tmp)
            ndf = self.get_downstream_nodes(this_tree, iNode_to_collapse)
            #print('ndf: ', ndf)
            for iNode_downstream in ndf: # iNodeToCollapse, includes source-collapser
                for iiNode in range(len(node_indices)):
                    #print('In loop: ', iNode_downstream, iiNode, node_indices[iiNode])
                    if iNode_downstream == node_indices[iiNode]:
                        #print('\tCollapse')
                        uncollapsed_v[iiNode] = 0
            nodes_collapsed.append(iNode_to_collapse)
            C.append(min(C_vec_tmp))
            #print(iiNode_to_collapse, iNode_to_collapse)
            # Collapse all downstream internal nodes
        return C, nodes_collapsed

    def print_tree(self, this_tree, C, nodes_collapsed, mean_y, sd_y):
        def print_tree_inner(this_tree, nodes_collapsed_choice, mean_y, sd_y):
            #print(this_tree[0][0])
            iDepth = int(this_tree[0][7])
            indent0 = ''
            for t in range(iDepth):
                indent0 = indent0 + '\t'
            if nodes_collapsed_choice.count(this_tree[0][6]) == 0 and not(np.isnan(this_tree[0][0])):
                print(indent0, this_tree[0][0:2])
                print_tree_inner(this_tree[1], nodes_collapsed_choice, mean_y, sd_y)
                print_tree_inner(this_tree[2], nodes_collapsed_choice, mean_y, sd_y)
            else:
                if len(this_tree[0][-1]) > 0:
                    m = np.nanmean(this_tree[0][-1])
                else:
                    m = 0 # Note: target values are normalized
                print(indent0, 'terminal node: ', mean_y + sd_y * m)
        if len(C) == 0:
            print('Empty tree.');
            return
        best_collapse_seq_end = np.argmin(C)
        nodes_collapsed_choice = nodes_collapsed[0:(best_collapse_seq_end + 1)]
        print_tree_inner(this_tree, nodes_collapsed_choice, mean_y, sd_y)

    def collapse_tree(self, this_tree, C, nodes_collapsed, mean_y, sd_y):
        def build_tree_inner(this_tree, nodes_collapsed_choice, mean_y, sd_y):
            if (nodes_collapsed_choice.count(this_tree[0][6]) == 0 and not(np.isnan(this_tree[0][0]))):
                to_report = this_tree[0][0:2]
                return [to_report, build_tree_inner(this_tree[1], nodes_collapsed_choice, mean_y, sd_y), build_tree_inner(this_tree[2], nodes_collapsed_choice, mean_y, sd_y)]
            else:
                if len(this_tree[0][-1]) > 0:
                    to_report = mean_y + sd_y * np.nanmean(this_tree[0][-1])
                else:
                    to_report = mean_y
                return to_report
        if len(C) == 0:
            return []
        best_collapse_seq_end = np.argmin(C)
        nodes_collapsed_choice = nodes_collapsed[0:(best_collapse_seq_end + 1)]
        return build_tree_inner(this_tree, nodes_collapsed_choice, mean_y, sd_y)

def tree_prediction(X, tree0):
    def tree_prediction_inner(xvec, current_tree):
        if not isinstance(current_tree, list):
            prediction = current_tree
        else:
            this_split_var = current_tree[0][0]
            this_split_val = current_tree[0][1]
            if (xvec[this_split_var] < this_split_val):
                branch = current_tree[1]
            else:
                branch = current_tree[2]
            if isinstance(branch, list):
                prediction = tree_prediction_inner(xvec, branch)
            else:
                prediction = branch
        return prediction
    y_pred = []
    for xrow in X:
        y_pred.append(tree_prediction_inner(xrow, tree0))
    return y_pred
