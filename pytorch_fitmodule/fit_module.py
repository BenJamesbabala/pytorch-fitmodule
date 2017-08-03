import numpy as np
import torch

from functools import partial
from torch.autograd import Variable
from torch.nn import CrossEntropyLoss, Module
from torch.optim import SGD

from .utils import add_metrics_to_log, Log, make_batches, ProgressBar


DEFAULT_LOSS = CrossEntropyLoss()
DEFAULT_OPTIMIZER = partial(SGD, lr=0.001, momentum=0.9)


class FitModule(Module):

    def fit(self,
            x=None,
            y=None,
            batch_size=32,
            epochs=1,
            verbose=1,
            validation_split=0.,
            validation_data=None,
            shuffle=True,
            initial_epoch=0,
            seed=None,
            loss=DEFAULT_LOSS,
            optimizer=DEFAULT_OPTIMIZER,
            metrics=None):
        """Trains the model similar to Keras' .fit(...) method

        # Arguments
            x: training data Tensor.
            y: target data Tensor.
            batch_size: integer. Number of samples per gradient update.
            epochs: integer, the number of times to iterate
                over the training data arrays.
            verbose: 0, 1. Verbosity mode.
                0 = silent, 1 = verbose.
            validation_split: float between 0 and 1:
                fraction of the training data to be used as validation data.
                The model will set apart this fraction of the training data,
                will not train on it, and will evaluate
                the loss and any model metrics
                on this data at the end of each epoch.
            validation_data: (x_val, y_val) tuple on which to evaluate
                the loss and any model metrics
                at the end of each epoch. The model will not
                be trained on this data.
            shuffle: boolean, whether to shuffle the training data
                before each epoch.
            initial_epoch: epoch at which to start training
                (useful for resuming a previous training run)
            seed: random seed.
            optimizer: training optimizer
            loss: training loss
            metrics: list of functions with signatures `metric(y_true, y_pred)`
                where y_true and y_pred are both Tensors

        # Returns
            list of Logs with training metrics
        """
        if seed and seed >= 0:
            np.random.seed(seed)
            torch.manual_seed(seed)
        # Prepare validation data
        if validation_data:
            val_x, val_y = validation_data
        elif validation_split and 0. < validation_split < 1.:
            split = int(x.size()[0] * (1. - validation_split))
            x, val_x = x[:split], x[split:]
            y, val_y = y[:split], y[split:]
        else:
            val_x, val_y = None, None
        # Compile optimizer
        opt = optimizer(self.parameters())
        # Run training loop
        logs = []
        self.train()
        n = x.size()[0]
        train_idxs = np.arange(n)
        for t in range(initial_epoch, epochs):
            if verbose:
                print("Epoch {0} / {1}".format(t+1, epochs))
            # Shuffle training set
            if shuffle:
                np.random.shuffle(train_idxs)
            # Get batches
            batches = make_batches(n, batch_size)
            # Setup logger
            if verbose:
                pb = ProgressBar(len(batches))
            n_run = 0
            log = Log()
            epoch_loss = 0.0
            # Run batches
            for batch_i, (batch_start, batch_end) in enumerate(batches):
                # Get batch data
                batch_idxs = train_idxs[batch_start : batch_end]
                batch_idxs = torch.from_numpy(batch_idxs).long()
                x_batch = Variable(x[batch_idxs])
                y_batch = Variable(y[batch_idxs])
                # Backprop
                opt.zero_grad()
                y_batch_pred = self(x_batch)
                batch_loss = loss(y_batch_pred, y_batch)
                batch_loss.backward()
                opt.step()
                # Update status
                n_run += batch_end - batch_start
                epoch_loss += batch_loss.data[0]
                log['train_loss'] = float(epoch_loss) / n_run
                if verbose:
                    pb.bar(batch_i, log.to_message())
            # Run metrics
            if metrics:
                y_train_pred = self.predict(x, batch_size)
                add_metrics_to_log(log, metrics, y, y_train_pred)
                if val_x is not None and val_y is not None:
                    y_val_pred = self.predict(val_x, batch_size)
                    add_metrics_to_log(log, metrics, val_y, y_val_pred, 'val_')
            logs.append(log)
            if verbose:
                pb.close(log.to_message())
        return logs

    def predict(self, x, batch_size=32):
        """Generates output predictions for the input samples.

        Computation is done in batches.

        # Arguments
            x: input data Tensor.
            batch_size: integer.

        # Returns
            prediction Tensor.
        """
        n = x.size()[0]
        train_idxs = np.arange(n)
        batches = make_batches(n, batch_size)
        self.eval()
        for batch_i, (batch_start, batch_end) in enumerate(batches):
            # Get batch data
            batch_idxs = train_idxs[batch_start : batch_end]
            batch_idxs = torch.from_numpy(batch_idxs).long()
            x_batch = Variable(x[batch_idxs])
            # Predict
            y_batch_pred = self(x_batch).data
            # Infer prediction shape
            if batch_i == 0:
                y_pred = torch.zeros((n,) + y_batch_pred.size()[1:])
            y_pred[batch_idxs] = y_batch_pred
        return y_pred
