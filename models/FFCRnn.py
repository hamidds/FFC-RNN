import torch.nn as nn
from FFCResnet import *
from SelfAttention import *


class CNN(nn.Module):

    def __init__(self, image_height=32, nc=1, leaky_relu=False):
        super(CNN, self).__init__()

        assert image_height % 16 == 0, 'imgH has to be a multiple of 16'

        kernel_sizes = [3, 3, 3, 3, 3, 3, 2]
        padding_sizes = [1, 1, 1, 1, 1, 1, 0]
        stride_sizes = [1, 1, 1, 1, 1, 1, 1]
        # nm = [64, 128, 256, 256, 512, 512, 512]
        nm = [32, 32, 48, 64, 80, 512, 512]

        cnn = nn.Sequential()

        def conv_relu(i, batch_normalization=False):
            input_channels = nc if i == 0 else nm[i - 1]
            output_channels = nm[i]

            cnn.add_module('conv{0}'.format(i),
                           nn.Conv2d(input_channels, output_channels, (kernel_sizes[i], kernel_sizes[i]),
                                     (stride_sizes[i], stride_sizes[i]), padding_sizes[i]))

            if batch_normalization:
                cnn.add_module('batchnorm{0}'.format(i), nn.BatchNorm2d(output_channels))
            if leaky_relu:
                cnn.add_module('relu{0}'.format(i), nn.LeakyReLU(0.2, inplace=True))
            else:
                cnn.add_module('relu{0}'.format(i), nn.ReLU(True))

        conv_relu(0)
        cnn.add_module('pooling{0}'.format(0), nn.MaxPool2d(2, 2))  # (64, img_height // 2, img_width // 2)
        conv_relu(1)
        cnn.add_module('pooling{0}'.format(1), nn.MaxPool2d(2, 2))  # (128, img_height // 4, img_width // 4)
        conv_relu(2)
        cnn.add_module('pooling{0}'.format(2), nn.MaxPool2d((2, 1)))  # (256, img_height // 8, img_width // 4)
        conv_relu(3)
        cnn.add_module('pooling{0}'.format(3), nn.MaxPool2d((1, 2)))  # 256 x 4 x 16
        conv_relu(4)

        # cnn.add_module('pooling{0}'.format(3), nn.MaxPool2d((1, 2)))
        # conv_relu(5)
        # cnn.add_module('pooling{0}'.format(3), nn.MaxPool2d((2, 2), (2, 1), (0, 1)))  # 512 x 2 x 16
        # conv_relu(6, True)  # 512 x 1 x 16

        self.cnn = cnn

    def forward(self, x):
        conv = self.cnn(x)
        return conv, 0


class BiLSTM(nn.Module):

    def __init__(self, input_size, hidden_size, dropout=0.5):
        super(BiLSTM, self).__init__()
        self.rnn = nn.LSTM(input_size, hidden_size, bidirectional=True)
        self.drp = nn.Dropout(dropout)

    def forward(self, x):
        recurrent, _ = self.rnn(x)
        recurrent = self.drp(recurrent)
        return recurrent


FEATURE_EXTRACTORS = {'cnn': {'model': CNN(image_height=32, nc=1), "output_channel": 80, "output_height": 4},
                      'ffc_resnet18': {'model': ffc_resnet18(), "output_channel": 512, "output_height": 1},
                      'ffc_resnet34': {'model': ffc_resnet34(), "output_channel": 512, "output_height": 1},
                      'ffc_resnet26': {'model': ffc_resnet26(), "output_channel": 2048, "output_height": 1},
                      'ffc_resnet50': {'model': ffc_resnet50(), "output_channel": 2048, "output_height": 1}}


class FFCRnn(nn.Module):

    def __init__(self, output_number, nh, n_rnn=2, map_to_seq_hidden=None, feature_extractor=None):
        super(FFCRnn, self).__init__()

        self.cnn = FEATURE_EXTRACTORS[feature_extractor]["model"]
        output_channel = FEATURE_EXTRACTORS[feature_extractor]["output_channel"]
        output_height = FEATURE_EXTRACTORS[feature_extractor]["output_height"]

        if map_to_seq_hidden is None:
            map_to_seq_hidden = output_channel

        self.attn = SelfAttention(output_channel, None)

        self.map_to_seq = nn.Linear(output_channel * output_height, map_to_seq_hidden)

        self.rnn = nn.Sequential()
        self.rnn.add_module('rnn{0}'.format(1), BiLSTM(map_to_seq_hidden, nh))

        for i in range(1, n_rnn):
            self.rnn.add_module('rnn{0}'.format(i + 1), BiLSTM(2 * nh, nh))

        # self.drp = nn.Dropout(0.5)
        # self.rnn1 = nn.LSTM(map_to_seq_hidden, nh, bidirectional=True)
        # self.rnn2 = nn.LSTM(2 * nh, nh, bidirectional=True)
        # self.rnn3 = nn.LSTM(2 * nh, nh, bidirectional=True)
        # self.rnn4 = nn.LSTM(2 * nh, nh, bidirectional=True)
        # self.rnn5 = nn.LSTM(2 * nh, nh, bidirectional=True)

        self.fc = nn.Linear(nh * 2, output_number)

    def forward(self, x):
        # conv features
        conv, _ = self.cnn(x)

        b, c, h, w = conv.size()
        print(conv.size())

        conv = self.attn(conv)

        # print(conv.size())
        conv = conv.view(b, c * h, w)
        conv = conv.permute(2, 0, 1)  # (width, batch, feature)

        seq = self.map_to_seq(conv)
        # print(seq.size())

        recurrent = self.rnn(seq)

        output = self.fc(recurrent)  # (seq_len, batch, num_class)

        return output


if __name__ == '__main__':
    # ffc_rnn = FFCRnn(32, 32, 32, 32)
    ffc_rnn = FFCRnn(output_number=41, nh=256, n_rnn=3, feature_extractor="ffc_resnet18")
    tensor = torch.zeros([10, 1, 32, 256], dtype=torch.float32)
    res = ffc_rnn(tensor)
    # ffc_rnn = FFCRnn(32, 1, 64, 64)
    # tensor = torch.zeros([10, 1, 32, 256], dtype=torch.float32)
    # res = ffc_rnn(tensor)
